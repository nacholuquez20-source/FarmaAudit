"""FastAPI application for AuditBot webhook and background jobs."""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
import json
import asyncio
import uuid
from collections import OrderedDict
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from pydantic import BaseModel
from supabase import create_client, Client

from config import get_settings
from models import WhatsAppPayload, ConversationState, RESPUESTA_CONFIG
from router import ConversationRouter
from meta_client import MetaClient
from supabase_manager import SupabaseManager
from init_supabase import init_supabase_schema

# NEW: Imports for perfumery audit v2
from audit_session import AuditState, get_session
from identity import resolve_responsable_by_sucursal, resolve_whatsapp_user, ventana_abierta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AuditBot", version="1.0.0")
settings = get_settings()
scheduler = AsyncIOScheduler()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


class EncargadoNotificationRequest(BaseModel):
    id_gestion: str
    telefono_encargado: str
    descripcion_desvio: str
    sucursal: str | None = None


class GestionRevisionRequest(BaseModel):
    accion: str  # 'aprobar' | 'rechazar' | 'en_gestion_terceros' | 'retomar'
    motivo: str | None = None
    plazo_dias: int | None = None


class CampaniaActivarRequest(BaseModel):
    sucursal_ids: list[str]
    plazo_dias: int | None = None


class InternalMessageRequest(BaseModel):
    comentario: str
    origen: str = "auditor"
    actor_id: str | None = None
    actor_nombre: str | None = None


class PanelUserCreateRequest(BaseModel):
    email: str
    password: str
    role: str
    nombre: str
    telefono: str | None = None
    id_sucursal: str | None = None
    permisos_modulos: list[str] = []


class PanelUserUpdateRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    role: str | None = None
    nombre: str | None = None
    telefono: str | None = None
    id_sucursal: str | None = None
    permisos_modulos: list[str] | None = None


class DesvioBorradorDiscardRequest(BaseModel):
    reason: str | None = None


# Lazy initialization - these will be created on demand
router = None
sheets = None

# Message deduplication cache: {message_id: (timestamp, phone)}
# TTL: 5 minutes (prevents reprocessing of Meta retries)
_processed_messages: OrderedDict = OrderedDict()
_processing_messages: set[str] = set()
_message_lock = asyncio.Lock()
_MESSAGE_TTL_SECONDS = 300
_supabase_client: Client | None = None
_dedup_store_available: bool | None = None
_last_reminder_sent: dict[str, tuple[datetime, int]] = {}  # {id_sesion: (last_reminder_timestamp, reminders_sent)}
_VALID_PANEL_ROLES = {"admin", "auditor", "sucursal"}
_VALID_MODULE_PERMISSIONS = {
    "dashboard",
    "gestion_desvios",
    "revision_desvios",
    "mis_desvios",
    "sucursales",
    "admin",
}
_DEFAULT_MODULES_BY_ROLE = {
    "admin": ["dashboard", "gestion_desvios", "revision_desvios", "mis_desvios", "sucursales", "admin"],
    "auditor": ["gestion_desvios", "revision_desvios", "sucursales"],
    "sucursal": ["dashboard", "mis_desvios", "sucursales"],
}
_MODULES_BY_ROLE = {
    "admin": _VALID_MODULE_PERMISSIONS,
    "auditor": {"gestion_desvios", "revision_desvios", "sucursales"},
    "sucursal": {"dashboard", "mis_desvios", "sucursales"},
}
_LEGACY_MODULE_ALIASES = {
    "desvios": "gestion_desvios",
}


def _json_list(value) -> list:
    """Return a list from json/text/list fields stored by Supabase."""
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _normalize_module_permissions(role: str, modules: list[str] | None = None) -> list[str]:
    """Return module permissions valid for the selected panel role."""
    if role not in _VALID_PANEL_ROLES:
        raise HTTPException(status_code=400, detail="Rol invalido")

    allowed = _MODULES_BY_ROLE[role]
    source = modules if modules is not None else _DEFAULT_MODULES_BY_ROLE[role]
    normalized: list[str] = []
    for module in source:
        module = _LEGACY_MODULE_ALIASES.get(module, module)
        if module not in _VALID_MODULE_PERMISSIONS:
            raise HTTPException(status_code=400, detail=f"Modulo invalido: {module}")
        if module in allowed and module not in normalized:
            normalized.append(module)
    return normalized


def _profile_from_user_and_row(user, profile: dict | None) -> dict:
    """Merge Supabase Auth user data with the panel profile row."""
    profile = profile or {}
    app_metadata = getattr(user, "app_metadata", None) or {}
    role = profile.get("role") or "auditor"
    return {
        "id": getattr(user, "id", None),
        "email": getattr(user, "email", None),
        "role": role,
        "nombre": profile.get("nombre") or getattr(user, "email", None),
        "telefono": profile.get("telefono"),
        "id_sucursal": profile.get("id_sucursal"),
        "permisos_modulos": _normalize_module_permissions(
            role,
            app_metadata.get("module_permissions") if isinstance(app_metadata.get("module_permissions"), list) else None,
        ),
    }


def _get_supabase_client() -> Client | None:
    """Create Supabase client lazily for distributed deduplication."""
    global _supabase_client, _dedup_store_available
    if _supabase_client is not None:
        return _supabase_client
    if _dedup_store_available is False:
        return None

    supabase_url = settings.supabase_url
    supabase_key = settings.supabase_service_key
    if not supabase_url or not supabase_key:
        _dedup_store_available = False
        return None

    try:
        _supabase_client = create_client(supabase_url, supabase_key)
        _dedup_store_available = True
    except Exception as exc:
        logger.warning(f"Supabase dedup disabled: client init failed: {exc}")
        _dedup_store_available = False
        return None

    return _supabase_client


def _claim_message_distributed(message_id: str, phone: str) -> bool:
    """Claim a message ID in shared storage to prevent cross-instance duplicates."""
    global _dedup_store_available
    client = _get_supabase_client()
    if client is None:
        return True

    try:
        client.table("webhook_dedup").insert({
            "message_id": message_id,
            "phone": phone,
            "claimed_at": datetime.utcnow().isoformat(),
        }).execute()
        return True
    except Exception as exc:
        error_text = str(exc).lower()
        if "duplicate key" in error_text or "already exists" in error_text or "23505" in error_text:
            return False
        if "webhook_dedup" in error_text and "does not exist" in error_text:
            logger.warning("Supabase dedup disabled: webhook_dedup table not found")
            _dedup_store_available = False
            return True
        logger.warning(f"Supabase dedup claim failed, falling back to in-memory only: {exc}")
        return True


def _release_message_distributed(message_id: str) -> None:
    """Release distributed claim on processing failure (allow safe retry)."""
    client = _get_supabase_client()
    if client is None:
        return
    try:
        client.table("webhook_dedup").delete().eq("message_id", message_id).execute()
    except Exception as exc:
        logger.warning(f"Failed to release distributed dedup claim for {message_id}: {exc}")


def _is_message_processed(message_id: str) -> bool:
    """Check if message was already processed (within TTL)."""
    if message_id not in _processed_messages:
        return False
    timestamp, _ = _processed_messages[message_id]
    if datetime.utcnow() - timestamp > timedelta(seconds=_MESSAGE_TTL_SECONDS):
        del _processed_messages[message_id]
        return False
    return True


async def _mark_message_processed(message_id: str, phone: str) -> None:
    """Mark message as processed."""
    async with _message_lock:
        _processed_messages[message_id] = (datetime.utcnow(), phone)
        _processing_messages.discard(message_id)
        if len(_processed_messages) > 1000:
            _processed_messages.popitem(last=False)


async def _claim_message_for_processing(message_id: str, phone: str) -> bool:
    """Atomically claim a message ID to avoid duplicate concurrent processing."""
    async with _message_lock:
        if _is_message_processed(message_id):
            return False
        if message_id in _processing_messages:
            return False
        if not _claim_message_distributed(message_id, phone):
            return False
        _processing_messages.add(message_id)
        return True


async def _release_message_claim(message_id: str) -> None:
    """Release in-flight claim if processing failed."""
    async with _message_lock:
        _processing_messages.discard(message_id)
    _release_message_distributed(message_id)

def get_router():
    """Get or create conversation router."""
    global router
    if router is None:
        router = ConversationRouter()
    return router

def get_sheets():
    """Get or create sheets manager."""
    global sheets
    if sheets is None:
        sheets = SupabaseManager()
    return sheets


async def _require_admin_or_auditor(request: Request) -> dict:
    """Validate Supabase JWT and require an admin/auditor profile."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "", 1).strip() if auth_header.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")

    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        user_response = client.auth.get_user(token)
        user = getattr(user_response, "user", None)
        user_id = getattr(user, "id", None)
        if not user_id:
            raise ValueError("Invalid token")

        profile_response = client.table("profiles").select("id, role, nombre").eq("id", user_id).maybe_single().execute()
        profile = profile_response.data or {}
        if profile.get("role") not in {"admin", "auditor"}:
            raise HTTPException(status_code=403, detail="Only admin/auditor can perform this action")
        return {"id": user_id, "role": profile.get("role"), "nombre": profile.get("nombre")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Auth validation failed: {exc}")
        raise HTTPException(status_code=401, detail="Invalid Authorization token")


async def _require_admin(request: Request) -> dict:
    """Validate Supabase JWT and require an admin profile."""
    profile = await _require_admin_or_auditor(request)
    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can perform this action")
    return profile


async def _require_profile(request: Request) -> dict:
    """Validate Supabase JWT and return the authenticated panel profile."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "", 1).strip() if auth_header.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")

    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        user_response = client.auth.get_user(token)
        user = getattr(user_response, "user", None)
        user_id = getattr(user, "id", None)
        if not user_id:
            raise ValueError("Invalid token")

        profile_response = (
            client.table("profiles")
            .select("id, role, nombre, id_sucursal")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        profile = profile_response.data or {}
        if not profile.get("role"):
            raise HTTPException(status_code=403, detail="Profile not found")
        return {
            "id": user_id,
            "role": profile.get("role"),
            "nombre": profile.get("nombre"),
            "id_sucursal": profile.get("id_sucursal"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Profile auth validation failed: {exc}")
        raise HTTPException(status_code=401, detail="Invalid Authorization token")


@app.on_event("startup")
async def startup_event():
    """Initialize background jobs on startup."""
    logger.info("Starting AuditBot...")
    init_supabase_schema()

    # Start scheduler
    scheduler.add_job(
        check_expired_confirmations,
        "interval",
        minutes=settings.timeout_check_interval,
        id="timeout_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        check_expired_audit_sessions,
        "interval",
        minutes=settings.timeout_check_interval,
        id="audit_timeout_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        check_expired_audit_sessions_v2,
        "interval",
        minutes=15,
        id="audit_v2_session_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        check_incomplete_respuestas_timeout,
        "interval",
        seconds=30,
        id="respuesta_timeout_check",
        max_instances=1,
    )
    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=23,  # UTC (20:00 ART = 23:00 UTC)
        minute=0,
        id="daily_summary",
        timezone=pytz.UTC,
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        regenerate_thumbnails_job,
        "interval",
        hours=1,  # Run every hour
        id="regenerate_thumbnails",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        check_overdue_gestion,
        "interval",
        minutes=15,
        id="overdue_gestion_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        remind_sla_auditor_revision,
        "interval",
        hours=1,
        id="sla_auditor_revision_check",
        max_instances=1,  # Prevent concurrent executions
    )
    scheduler.add_job(
        remind_responsable_desvios_pendientes,
        "cron",
        hour=13,  # UTC (10:00 ART)
        minute=0,
        id="responsable_desvios_reminder",
        timezone=pytz.UTC,
        max_instances=1,  # Prevent concurrent executions
    )
    # Disabled: Using Supabase directly, no longer syncing from Google Sheets
    # scheduler.add_job(
    #     sync_sheets_to_supabase,
    #     "interval",
    #     minutes=5,
    #     id="sheets_supabase_sync",
    #     max_instances=1,
    # )
    scheduler.start()

    logger.info("Background jobs started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    scheduler.shutdown()
    logger.info("AuditBot shutdown")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/send-encargado-notification")
async def send_encargado_notification(payload: EncargadoNotificationRequest, request: Request):
    """Send a WhatsApp notification to the branch manager for one deviation."""
    await _require_admin_or_auditor(request)
    telefono = "".join(ch for ch in payload.telefono_encargado if ch.isdigit())
    if not telefono:
        raise HTTPException(status_code=400, detail="telefono_encargado is required")

    gestion = get_sheets().get_gestion_by_id(payload.id_gestion)
    sucursal = payload.sucursal or (gestion or {}).get("sucursal") or "tu sucursal"
    descripcion = payload.descripcion_desvio or (gestion or {}).get("desvio") or "desvio pendiente"
    if len(descripcion) > 420:
        descripcion = f"{descripcion[:417]}..."

    message = (
        f"FarmaAudit: tenes un desvio pendiente para corregir en {sucursal}.\n\n"
        f"ID: {payload.id_gestion}\n"
        f"Detalle: {descripcion}\n\n"
        "Responde este WhatsApp para ver tus desvios pendientes, seleccionar uno y enviar la correccion."
    )

    meta_client = MetaClient()
    sent = await meta_client.send_text(telefono, message)
    if not sent:
        raise HTTPException(status_code=502, detail="No se pudo enviar el WhatsApp")

    return {"status": "ok"}


@app.post("/api/gestion/{id_gestion}/mensajes")
async def create_internal_message(id_gestion: str, payload: InternalMessageRequest, request: Request):
    """Create an internal timeline message for one managed deviation."""
    profile = await _require_profile(request)
    comentario = (payload.comentario or "").strip()
    if not comentario:
        raise HTTPException(status_code=400, detail="comentario is required")

    if payload.origen not in {"auditor", "sucursal"}:
        raise HTTPException(status_code=400, detail="origen must be auditor or sucursal")

    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    gestion_response = (
        client.table("gestion")
        .select("id_gestion, id_sucursal")
        .eq("id_gestion", id_gestion)
        .maybe_single()
        .execute()
    )
    gestion = gestion_response.data
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestion not found")

    if profile["role"] == "sucursal" and profile.get("id_sucursal") != gestion.get("id_sucursal"):
        raise HTTPException(status_code=403, detail="No autorizado para esta gestion")

    actor_id = profile["id"]
    actor_nombre = profile.get("nombre") or "Usuario"
    event_response = (
        client.table("desvio_eventos")
        .insert({
            "id_gestion": id_gestion,
            "tipo": "mensaje",
            "comentario": comentario,
            "actor_id": actor_id,
            "actor_nombre": actor_nombre,
            "metadata": {
                "origen": payload.origen,
                "leido_por_auditor": payload.origen == "auditor",
                "leido_por_sucursal": payload.origen == "sucursal",
            },
        })
        .execute()
    )
    data = event_response.data or []
    return data[0] if data else {"status": "ok"}


@app.get("/api/gestion/{id_gestion}/responsable-activo")
async def get_responsable_activo(id_gestion: str, request: Request):
    """Resuelve en vivo el responsable_sucursal activo de la sucursal de esta
    gestion, si la ventana de 24h de Meta esta abierta, y cuantos desvios
    abiertos tiene la sucursal (para el boton de recordatorio del detalle de
    desvio, que manda un solo mensaje por sucursal, no uno por desvio). El
    frontend no puede leer usuarios_whatsapp directo (RLS admin-only), y lo
    necesitan tambien los auditores."""
    await _require_admin_or_auditor(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    gestion_response = (
        client.table("gestion").select("id_sucursal").eq("id_gestion", id_gestion).maybe_single().execute()
    )
    gestion = gestion_response.data
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestion not found")

    id_sucursal = gestion["id_sucursal"]
    db = SupabaseManager()
    grupo = db.get_desvios_abiertos_por_sucursal(id_sucursal)
    cantidad_desvios_abiertos = grupo["cantidad"] if grupo else 0

    ultimo_recordatorio = db.get_ultimo_recordatorio_enviado(id_sucursal)
    proximo_disponible_at = None
    if ultimo_recordatorio and ultimo_recordatorio.get("enviado_at"):
        enviado_at = datetime.fromisoformat(ultimo_recordatorio["enviado_at"].replace("Z", "+00:00"))
        proximo = enviado_at + timedelta(hours=RECORDATORIO_COOLDOWN_HORAS)
        if datetime.now(timezone.utc) < proximo:
            proximo_disponible_at = proximo.isoformat()

    responsable = resolve_responsable_by_sucursal(id_sucursal)
    if not responsable:
        return {
            "responsable": None,
            "ventana_abierta": False,
            "cantidad_desvios_abiertos": cantidad_desvios_abiertos,
            "proximo_disponible_at": proximo_disponible_at,
        }

    return {
        "responsable": {"nombre": responsable.nombre, "telefono": responsable.telefono},
        "ventana_abierta": ventana_abierta(responsable),
        "cantidad_desvios_abiertos": cantidad_desvios_abiertos,
        "proximo_disponible_at": proximo_disponible_at,
    }


@app.get("/api/sucursales/estado-contacto")
async def get_estado_contacto_sucursales(request: Request):
    """Para todas las sucursales activas a la vez: quién es el encargado (si
    hay), si su ventana de 24h está abierta, y cuándo fue el último
    recordatorio enviado. usuarios_whatsapp es RLS admin-only y el auditor la
    necesita para saber si el botón de recordatorio tiene sentido — mismo
    motivo que /api/gestion/{id}/responsable-activo, en lote."""
    await _require_admin_or_auditor(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    sucursales_resp = client.table("sucursales").select("id").eq("activo", True).execute()
    ids_sucursal = [row["id"] for row in (sucursales_resp.data or [])]

    responsables_resp = (
        client.table("usuarios_whatsapp")
        .select("id_sucursal, nombre, telefono, ultimo_mensaje_entrante_at")
        .eq("rol", "responsable_sucursal")
        .eq("activo", True)
        .execute()
    )
    responsables_por_sucursal = {
        row["id_sucursal"]: row for row in (responsables_resp.data or []) if row.get("id_sucursal")
    }

    recordatorios_resp = (
        client.table("recordatorios_sucursal")
        .select("id_sucursal, enviado_at")
        .eq("resultado", "enviado")
        .order("enviado_at", desc=True)
        .execute()
    )
    ultimo_recordatorio_por_sucursal: Dict[str, str] = {}
    for row in recordatorios_resp.data or []:
        # El primero que aparece por sucursal es el mas reciente, por el order() de arriba.
        ultimo_recordatorio_por_sucursal.setdefault(row["id_sucursal"], row["enviado_at"])

    resultado = []
    for id_sucursal in ids_sucursal:
        r = responsables_por_sucursal.get(id_sucursal)
        ultimo_mensaje = r.get("ultimo_mensaje_entrante_at") if r else None
        abierta = False
        if ultimo_mensaje:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(ultimo_mensaje.replace("Z", "+00:00"))
            abierta = delta.total_seconds() < 24 * 3600

        ultimo_recordatorio = ultimo_recordatorio_por_sucursal.get(id_sucursal)
        proximo_disponible = None
        if ultimo_recordatorio:
            enviado_at = datetime.fromisoformat(ultimo_recordatorio.replace("Z", "+00:00"))
            proximo = enviado_at + timedelta(hours=RECORDATORIO_COOLDOWN_HORAS)
            if datetime.now(timezone.utc) < proximo:
                proximo_disponible = proximo.isoformat()

        resultado.append({
            "id_sucursal": id_sucursal,
            "encargado_nombre": r.get("nombre") if r else None,
            "encargado_telefono": r.get("telefono") if r else None,
            "tiene_telefono": bool(r and r.get("telefono")),
            "ventana_abierta": abierta,
            "ultimo_recordatorio_at": ultimo_recordatorio,
            "proximo_disponible_at": proximo_disponible,
        })

    return {"sucursales": resultado}


@app.post("/api/sucursales/{id_sucursal}/recordatorio")
async def post_recordatorio_sucursal(id_sucursal: str, request: Request):
    """El botón manual de "reclamar por WhatsApp". Nunca manda la plantilla
    fuera de la ventana de 24h (farmaaudit_novedades sigue sin aprobar) — en
    ese caso devuelve sin_ventana para que el frontend ofrezca el link manual
    de wa.me en su lugar."""
    profile = await _require_admin_or_auditor(request)
    db = SupabaseManager()

    group = db.get_desvios_abiertos_por_sucursal(id_sucursal)
    if not group:
        raise HTTPException(status_code=404, detail="La sucursal no tiene desvíos abiertos")

    meta_client = MetaClient()
    resultado = await _enviar_recordatorio_sucursal(
        db, meta_client, id_sucursal, group, canal="manual", enviado_por=profile.get("id")
    )

    if resultado["resultado"] == "cooldown":
        raise HTTPException(status_code=429, detail=resultado)
    if resultado["resultado"] == "sin_encargado":
        raise HTTPException(status_code=409, detail=resultado)
    if resultado["resultado"] == "sin_ventana":
        raise HTTPException(status_code=409, detail=resultado)
    if resultado["resultado"] == "fallido":
        raise HTTPException(status_code=502, detail=resultado)

    return resultado


@app.post("/api/gestion/{id_gestion}/revision")
async def revisar_gestion(id_gestion: str, payload: GestionRevisionRequest, request: Request):
    """Approve/reject a branch manager's correction, or flag/unblock a deviation that
    depends on third parties (see ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 1)."""
    profile = await _require_admin_or_auditor(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    accion = (payload.accion or "").strip()
    if accion not in {"aprobar", "rechazar", "en_gestion_terceros", "retomar"}:
        raise HTTPException(status_code=400, detail="accion invalida")

    gestion_response = client.table("gestion").select("*").eq("id_gestion", id_gestion).maybe_single().execute()
    gestion = gestion_response.data
    if not gestion:
        raise HTTPException(status_code=404, detail="Gestion not found")

    motivo = (payload.motivo or "").strip()
    if accion in {"rechazar", "en_gestion_terceros"} and not motivo:
        raise HTTPException(status_code=400, detail="El motivo es obligatorio")

    actor_id = profile["id"]
    actor_nombre = profile.get("nombre") or "Auditor"
    now = datetime.now(timezone.utc)
    db = get_sheets()

    veces_rechazado = int(gestion.get("veces_rechazado") or 0)
    evento_tipo = "nota"
    evento_comentario = motivo

    if accion == "aprobar":
        updates = {
            "estado": "Resuelta",
            "cerrado_por": actor_nombre,
            "en_revision_desde": None,
        }
        evento_tipo = "cierre"
        evento_comentario = motivo or "Correccion aprobada por el auditor."
    elif accion == "rechazar":
        plazo_dias = payload.plazo_dias or 2
        nueva_plazo = (now + timedelta(days=plazo_dias)).strftime("%Y-%m-%d")
        veces_rechazado += 1
        updates = {
            "estado": "En_proceso",
            "plazo_fecha": nueva_plazo,
            "plazo_fecha_original": gestion.get("plazo_fecha_original") or gestion.get("plazo_fecha"),
            "veces_rechazado": veces_rechazado,
            "en_revision_desde": None,
        }
        evento_tipo = "rechazo"
    elif accion == "en_gestion_terceros":
        updates = {"estado": "En_gestion_terceros", "en_revision_desde": None}
    else:  # retomar
        updates = {"estado": "En_proceso"}
        evento_comentario = motivo or "Se retoma la gestion del desvio."

    db.update_gestion_fields(id_gestion, updates)

    client.table("desvio_eventos").insert({
        "id_gestion": id_gestion,
        "tipo": evento_tipo,
        "comentario": evento_comentario,
        "actor_id": actor_id,
        "actor_nombre": actor_nombre,
        "metadata": {"accion": accion},
    }).execute()

    try:
        client.table("desvio_notificaciones").update({"leida": True}).eq("id_gestion", id_gestion).eq(
            "tipo", "encargado_respondio"
        ).eq("leida", False).execute()
    except Exception as exc:
        logger.warning(f"Failed to mark notifications read for {id_gestion}: {exc}")

    telefono = "".join(ch for ch in str(gestion.get("tel_responsable") or "") if ch.isdigit())
    if telefono and accion in {"aprobar", "rechazar"}:
        meta_client = MetaClient()
        try:
            if accion == "aprobar":
                mensaje = f"FarmaAudit: tu correccion para \"{gestion.get('desvio')}\" fue aprobada. Gracias!"
            else:
                mensaje = (
                    f"FarmaAudit: tu correccion para \"{gestion.get('desvio')}\" fue rechazada.\n"
                    f"Motivo: {motivo}\n"
                    "Responde este WhatsApp para verla de nuevo y volver a enviar la correccion."
                )
            await meta_client.send_text(telefono, mensaje)
        except Exception as exc:
            logger.warning(f"Failed to send WhatsApp feedback for {id_gestion}: {exc}")

        if accion == "rechazar" and veces_rechazado >= 3 and settings.coordinador_tel:
            try:
                await meta_client.send_text(
                    settings.coordinador_tel,
                    f"FarmaAudit: el desvio {id_gestion} ({gestion.get('sucursal')}) fue rechazado "
                    f"{veces_rechazado} veces. Requiere seguimiento.",
                )
            except Exception as exc:
                logger.warning(f"Failed to alert coordinator about repeated rejection {id_gestion}: {exc}")

    updated_response = client.table("gestion").select("*").eq("id_gestion", id_gestion).maybe_single().execute()
    return updated_response.data or {"status": "ok"}


@app.post("/api/campanias/{campania_id}/activar")
async def activar_campania(campania_id: str, payload: CampaniaActivarRequest, request: Request):
    """Genera las tareas de campania (accion x sucursal) para las sucursales elegidas
    y activa la campania. El envio de WhatsApp es best-effort: requiere templates
    aprobados en Meta Business Manager (ver ARQUITECTURA_DESVIOS_CAMPANIAS.md,
    seccion 2.4 bis) que todavia pueden no estar registrados, asi que se intenta
    y se ignora el fallo sin bloquear la activacion (mismo criterio que el resto
    del bot, p. ej. send_alerta_coordinador)."""
    await _require_admin_or_auditor(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    if not payload.sucursal_ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos una sucursal")

    campania_response = client.table("campanias").select("*").eq("id", campania_id).maybe_single().execute()
    campania = campania_response.data
    if not campania:
        raise HTTPException(status_code=404, detail="Campania not found")

    acciones_response = client.table("campania_acciones").select("*").eq("campania_id", campania_id).execute()
    acciones = acciones_response.data or []
    if not acciones:
        raise HTTPException(status_code=400, detail="La campania no tiene acciones cargadas")

    sucursales_response = (
        client.table("sucursales")
        .select("id, nombre, responsable, tel_responsable")
        .in_("id", payload.sucursal_ids)
        .execute()
    )
    sucursales = {row["id"]: row for row in (sucursales_response.data or [])}

    plazo_dias = payload.plazo_dias or 14
    plazo_fecha = (datetime.now(timezone.utc) + timedelta(days=plazo_dias)).strftime("%Y-%m-%d")

    tareas_nuevas = []
    for sucursal_id in payload.sucursal_ids:
        sucursal = sucursales.get(sucursal_id)
        if not sucursal:
            continue
        for accion in acciones:
            tareas_nuevas.append({
                "campania_id": campania_id,
                "accion_id": accion["id"],
                "id_sucursal": sucursal_id,
                "responsable": sucursal.get("responsable"),
                "tel_responsable": sucursal.get("tel_responsable"),
                "estado": "Pendiente",
                "plazo_fecha": plazo_fecha,
            })

    if not tareas_nuevas:
        raise HTTPException(status_code=400, detail="No se encontraron sucursales validas")

    client.table("campanias").update({
        "estado": "Activa",
        "fecha_inicio": campania.get("fecha_inicio") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }).eq("id", campania_id).execute()

    client.table("campania_tareas").insert(tareas_nuevas).execute()

    tareas_por_sucursal: dict[str, int] = {}
    for tarea in tareas_nuevas:
        tareas_por_sucursal[tarea["id_sucursal"]] = tareas_por_sucursal.get(tarea["id_sucursal"], 0) + 1

    meta_client = MetaClient()
    campania_nombre = campania.get("nombre") or "campania"
    for sucursal_id, cantidad in tareas_por_sucursal.items():
        sucursal = sucursales.get(sucursal_id) or {}
        telefono = "".join(ch for ch in str(sucursal.get("tel_responsable") or "") if ch.isdigit())
        if not telefono:
            continue
        sent = await meta_client.send_template(
            telefono,
            "campana_nueva_sucursal",
            body_params=[sucursal.get("nombre") or "", campania_nombre, str(cantidad)],
        )
        if not sent:
            logger.warning(
                f"No se pudo enviar el template de campania a la sucursal {sucursal_id} "
                f"(campania {campania_id}) — probablemente el template no esta aprobado aun en Meta."
            )

    return {"status": "ok", "tareas_creadas": len(tareas_nuevas)}


@app.get("/api/admin/panel-users")
async def list_panel_users(request: Request):
    """List Auth users merged with panel profile and module permissions."""
    await _require_admin(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    profiles_response = client.table("profiles").select("id, role, nombre, telefono, id_sucursal").execute()
    profiles = {row["id"]: row for row in (profiles_response.data or [])}
    users = client.auth.admin.list_users(page=1, per_page=1000)
    return [_profile_from_user_and_row(user, profiles.get(getattr(user, "id", ""))) for user in users]


@app.post("/api/admin/panel-users")
async def create_panel_user(payload: PanelUserCreateRequest, request: Request):
    """Create a Supabase Auth user and its panel profile."""
    await _require_admin(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    nombre = (payload.nombre or "").strip() or email
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalido")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="La contrasena debe tener al menos 6 caracteres")

    modules = _normalize_module_permissions(payload.role, payload.permisos_modulos)
    if payload.role == "sucursal" and not payload.id_sucursal:
        raise HTTPException(status_code=400, detail="Los responsables necesitan una sucursal")

    try:
        user_response = client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"module_permissions": modules},
            "user_metadata": {"nombre": nombre},
        })
        user = getattr(user_response, "user", None)
        user_id = getattr(user, "id", None)
        if not user_id:
            raise ValueError("Supabase no devolvio el usuario creado")

        profile_payload = {
            "id": user_id,
            "role": payload.role,
            "nombre": nombre,
            "telefono": payload.telefono or None,
            "id_sucursal": payload.id_sucursal if payload.role == "sucursal" else None,
        }
        profile_response = client.table("profiles").upsert(profile_payload).execute()
        profile = (profile_response.data or [profile_payload])[0]
        return _profile_from_user_and_row(user, profile)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to create panel user {email}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo crear el usuario")


@app.patch("/api/admin/panel-users/{user_id}")
async def update_panel_user(user_id: str, payload: PanelUserUpdateRequest, request: Request):
    """Update Auth credentials/metadata and panel profile fields."""
    await _require_admin(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    current_user_response = client.auth.admin.get_user_by_id(user_id)
    current_user = getattr(current_user_response, "user", None)
    if not current_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    profile_response = client.table("profiles").select("id, role, nombre, telefono, id_sucursal").eq("id", user_id).maybe_single().execute()
    current_profile = profile_response.data or {}
    role = payload.role or current_profile.get("role") or "auditor"
    modules = _normalize_module_permissions(
        role,
        payload.permisos_modulos if payload.permisos_modulos is not None else None,
    )
    if payload.permisos_modulos is None:
        current_metadata = getattr(current_user, "app_metadata", None) or {}
        current_modules = current_metadata.get("module_permissions")
        modules = _normalize_module_permissions(role, current_modules if isinstance(current_modules, list) else None)

    id_sucursal = payload.id_sucursal if payload.id_sucursal is not None else current_profile.get("id_sucursal")
    if role == "sucursal" and not id_sucursal:
        raise HTTPException(status_code=400, detail="Los responsables necesitan una sucursal")

    auth_patch: dict = {"app_metadata": {**(getattr(current_user, "app_metadata", None) or {}), "module_permissions": modules}}
    if payload.email:
        email = payload.email.strip().lower()
        if "@" not in email:
            raise HTTPException(status_code=400, detail="Email invalido")
        auth_patch["email"] = email
        auth_patch["email_confirm"] = True
    if payload.password:
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="La contrasena debe tener al menos 6 caracteres")
        auth_patch["password"] = payload.password

    try:
        updated_user_response = client.auth.admin.update_user_by_id(user_id, auth_patch)
        updated_user = getattr(updated_user_response, "user", None) or current_user

        profile_payload = {
            "id": user_id,
            "role": role,
            "nombre": payload.nombre if payload.nombre is not None else current_profile.get("nombre") or getattr(updated_user, "email", None),
            "telefono": payload.telefono if payload.telefono is not None else current_profile.get("telefono"),
            "id_sucursal": id_sucursal if role == "sucursal" else None,
        }
        saved_profile_response = client.table("profiles").upsert(profile_payload).execute()
        saved_profile = (saved_profile_response.data or [profile_payload])[0]
        return _profile_from_user_and_row(updated_user, saved_profile)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update panel user {user_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo guardar el usuario")


@app.api_route("/api/desvios-borrador/{draft_id}/approve", methods=["POST", "GET", "OPTIONS"])
@app.api_route("/desvios-borrador/{draft_id}/approve", methods=["POST", "GET", "OPTIONS"])
async def approve_desvio_borrador(draft_id: str, request: Request):
    """Approve a WhatsApp draft and convert it to gestion/reportes."""
    if request.method == "OPTIONS":
        return {"status": "ok"}
    profile = await _require_admin_or_auditor(request)
    try:
        result = get_sheets().approve_desvio_borrador(draft_id, str(profile["id"]))
        return {"status": "ok", **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Failed to approve desvio borrador {draft_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo aprobar el borrador")


@app.api_route("/api/desvios-borrador/{draft_id}/discard", methods=["POST", "GET", "OPTIONS"])
@app.api_route("/desvios-borrador/{draft_id}/discard", methods=["POST", "GET", "OPTIONS"])
async def discard_desvio_borrador(
    draft_id: str,
    request: Request,
    payload: DesvioBorradorDiscardRequest | None = None,
):
    """Discard a WhatsApp draft without deleting the audit trail."""
    if request.method == "OPTIONS":
        return {"status": "ok"}
    profile = await _require_admin_or_auditor(request)
    try:
        result = get_sheets().discard_desvio_borrador(
            draft_id,
            str(profile["id"]),
            (payload.reason if payload else "") or "",
        )
        return {"status": "ok", **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Failed to discard desvio borrador {draft_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo descartar el borrador")


# @app.get("/sync-now")
# async def sync_now():
#     """Manual sync endpoint for testing."""
#     # Disabled: using Supabase directly, no longer syncing from Google Sheets
#     pass


@app.get("/webhook")
async def webhook_verify(request: Request):
    """Meta WhatsApp webhook verification (GET)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.meta_verify_token:
        logger.info("Webhook verified with Meta")
        return PlainTextResponse(challenge)
    else:
        logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == settings.meta_verify_token}")
        raise HTTPException(status_code=403, detail="Forbidden")


def _verify_meta_signature(body: bytes, signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 header sent by Meta. Returns True if valid or if no secret is configured."""
    app_secret = settings.meta_app_secret
    if not app_secret:
        return True  # Verification disabled — set META_APP_SECRET in production
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header, expected)


@app.post("/webhook")
async def webhook(request: Request):
    """Meta WhatsApp Cloud API webhook entry point."""
    correlation_id = str(uuid.uuid4())[:8]  # Short correlation ID for logs
    message_id = ""
    message_claimed = False
    processed_successfully = False
    try:
        body_bytes = await request.body()
        sig = request.headers.get("x-hub-signature-256", "")
        if not _verify_meta_signature(body_bytes, sig):
            logger.warning(f"[{correlation_id}] Webhook signature mismatch — rejected")
            raise HTTPException(status_code=403, detail="Invalid signature")
        data = json.loads(body_bytes)

        # Extract messages from Meta's nested structure
        entry = data.get("entry", [])
        if not entry:
            logger.debug(f"[{correlation_id}] Webhook received but no entry data")
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            logger.debug(f"[{correlation_id}] Webhook received but no changes")
            return {"status": "ok"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.debug(f"[{correlation_id}] Webhook received but no messages (might be status update)")
            return {"status": "ok"}

        msg = messages[0]
        telefono = msg.get("from", "")
        if not telefono:
            logger.warning(f"[{correlation_id}] Received payload without from number")
            return {"status": "invalid_payload"}

        # Normalize phone to digits only
        telefono = "".join(ch for ch in telefono if ch.isdigit())

        # Check for duplicate message (Meta redelivery protection)
        message_id = msg.get("id", "")
        context_message_id = str((msg.get("context") or {}).get("id") or "")
        if message_id:
            message_claimed = await _claim_message_for_processing(message_id, telefono)
            if not message_claimed:
                logger.info(f"[{correlation_id}] Duplicate/in-flight message detected (msg_id: {message_id}, phone: {telefono}). Skipping.")
                return {"status": "ok", "result": "duplicate_skipped"}

        # Extract message content based on type
        tipo = msg.get("type", "text")
        contenido = None
        media_url = None
        media_id = None
        mime_type = None

        if tipo == "text":
            contenido = msg.get("text", {}).get("body", "")
        elif tipo == "audio":
            audio = msg.get("audio", {})
            media_id = audio.get("id")
            mime_type = audio.get("mime_type")
            if media_id:
                # TODO: Download audio from Meta API using media_id
                # media_url = await _get_meta_media_url(media_id)
                contenido = f"[Audio message {media_id}]"
        elif tipo == "image":
            image = msg.get("image", {})
            media_id = image.get("id")
            mime_type = image.get("mime_type")
            contenido = image.get("caption", "")
            if media_id:
                # TODO: Download image from Meta API using media_id
                # media_url = await _get_meta_media_url(media_id)
                pass
        elif tipo == "interactive":
            # Handle interactive messages (list selections, button clicks)
            interactive = msg.get("interactive", {})

            # List reply (from list message)
            if "list_reply" in interactive:
                contenido = interactive["list_reply"].get("id", "")
                tipo = "text"  # Treat as text for downstream handlers
            # Button reply (from quick reply buttons)
            elif "button_reply" in interactive:
                contenido = interactive["button_reply"].get("id", "")
                tipo = "text"  # Treat as text for downstream handlers
            else:
                contenido = ""
                tipo = "text"

        payload = WhatsAppPayload(
            telefono=telefono,
            tipo=tipo,
            contenido=contenido,
            media_url=media_url,
            media_id=media_id,
            mime_type=mime_type,
            message_id=message_id,
            context_message_id=context_message_id,
        )

        logger.info(
            f"[{correlation_id}] Received message from {payload.telefono} "
            f"(type: {payload.tipo}, msg_id: {message_id}, context_id: {context_message_id or 'none'})"
        )

        meta_client = MetaClient()
        route = get_router()

        # Identidad se resuelve acá, antes de cualquier rama de sesión. Antes
        # de esto, un teléfono con una fila vieja en sesiones_whatsapp
        # entraba directo al flujo v2 sin haberse verificado contra ninguna
        # tabla (bastaba con haber iniciado una auditoría alguna vez).
        whatsapp_user = resolve_whatsapp_user(payload.telefono)
        if not whatsapp_user or not whatsapp_user.activo:
            logger.warning(
                f"[{correlation_id}] Telefono no registrado o inactivo: {payload.telefono}"
            )
            await meta_client.send_text(
                payload.telefono,
                "❌ No estás registrado. Contactá al coordinador.",
            )
            result = "unknown_or_inactive_phone"
        else:
            # No bloqueante: la ventana de 24h de Meta se calcula a partir de
            # esto, pero un fallo acá no puede tirar abajo el procesamiento
            # del mensaje en sí.
            try:
                SupabaseManager().update_ultimo_mensaje_entrante(whatsapp_user.id)
            except Exception as exc:
                logger.warning(f"[{correlation_id}] Failed to update ultimo_mensaje_entrante: {exc}")

            # Route to v2 handler while there is any active v2 session (including DONE state,
            # which still expects responsable name and ficha-download answer)
            session = get_session(payload.telefono)
            if session:
                result = await route.handle_perfumeria_audit(payload, meta_client)
            else:
                result = await route.handle_message(payload, meta_client)

        # Mark message as processed (after successful processing)
        if message_id:
            await _mark_message_processed(message_id, telefono)
            processed_successfully = True

        logger.info(f"[{correlation_id}] Processed message result: {result}")
        return {"status": "ok", "result": result}
    except Exception as e:
        import traceback
        logger.error(f"[{correlation_id}] Webhook error: {e}")
        logger.error(f"[{correlation_id}] Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}
    finally:
        if message_id and message_claimed and not processed_successfully:
            await _release_message_claim(message_id)


async def check_expired_confirmations():
    """Background job: Check and remove expired pending confirmations."""
    try:
        sheets = get_sheets()
        expired = sheets.get_expired_pendientes()
        meta_client = MetaClient()

        for pendiente in expired:
            logger.info(f"Timeout expired for {pendiente.telefono_auditor}")

            # Notify auditor
            await meta_client.send_text(
                pendiente.telefono_auditor,
                "â° Tu confirmaciÃ³n expirÃ³. EnvÃ­ame un nuevo hallazgo cuando estÃ©s listo.",
            )

            # Reset conversation state
            sheets.update_conversacion(
                telefono=pendiente.telefono_auditor,
                estado=ConversationState.IDLE,
            )

            # Delete pendiente
            sheets.delete_pendiente(pendiente.id_temp)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired confirmations")
    except Exception as e:
        logger.error(f"Error in timeout check job: {e}")


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


async def check_incomplete_respuestas_timeout():
    """Background job: prompt, auto-complete or discard incomplete collected responses."""
    try:
        sheets = get_sheets()
        meta_client = MetaClient()
        route = get_router()
        respuestas = sheets.get_respuestas_incompletas_timeout(
            RESPUESTA_CONFIG["timeout_sin_actividad_segundos"]
        )
        now = datetime.now(timezone.utc)

        for respuesta in respuestas:
            last_message = _parse_utc_timestamp(respuesta.timestamp_ultimo_mensaje)
            if not last_message:
                continue

            inactive_seconds = (now - last_message).total_seconds()
            if inactive_seconds >= RESPUESTA_CONFIG["timeout_max_segundos"]:
                sheets.update_respuesta_pregunta(
                    respuesta.id,
                    estado="descartada",
                    razon_descarte="timeout_max",
                )
                sheets.create_respuesta_audit_log(
                    respuesta.id,
                    "descartada_timeout",
                    {"segundos": inactive_seconds},
                )
                conv = sheets.get_conversacion(respuesta.telefono_auditor)
                context = {}
                if conv and conv.ultimo_mensaje:
                    try:
                        context = json.loads(conv.ultimo_mensaje)
                    except Exception:
                        context = {}

                if context.get("quoted_clarification"):
                    try:
                        resume_state = ConversationState(str(context.get("return_state") or ConversationState.EN_BLOQUE_PERFUMERIA.value))
                    except ValueError:
                        resume_state = ConversationState.EN_BLOQUE_PERFUMERIA
                    sheets.update_conversacion(
                        telefono=respuesta.telefono_auditor,
                        estado=resume_state,
                        id_pendiente=respuesta.id_sesion,
                        id_respuesta_actual="",
                    )
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "Cierre la aclaracion por inactividad y mantuve la auditoria en curso. Podes seguir con el bloque actual.",
                    )
                else:
                    sheets.update_conversacion(
                        telefono=respuesta.telefono_auditor,
                        estado=ConversationState.IDLE,
                        id_respuesta_actual="",
                    )
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "Timeout: tu respuesta fue descartada por inactividad. Escribi INICIO para retomar.",
                    )
                continue

            if (
                RESPUESTA_CONFIG.get("auto_complete_enabled", False)
                and inactive_seconds >= RESPUESTA_CONFIG["timeout_auto_complete_segundos"]
            ):
                conv = sheets.get_conversacion(respuesta.telefono_auditor)
                payload = WhatsAppPayload(
                    telefono=respuesta.telefono_auditor,
                    tipo="text",
                    contenido="LISTO",
                )
                if conv:
                    await meta_client.send_text(
                        respuesta.telefono_auditor,
                        "Auto-completando tu respuesta por inactividad...",
                    )
                    await route._complete_respuesta_collection(  # noqa: SLF001 - internal orchestration for scheduler
                        respuesta,
                        conv,
                        payload,
                        meta_client,
                        auto_complete=True,
                        force=True,
                    )
                continue

            if not respuesta.timeout_prompt_enviado:
                await meta_client.send_text(
                    respuesta.telefono_auditor,
                    "Ya terminaste de enviar tu respuesta? Escribi LISTO para continuar, o segui enviando mensajes.",
                )
                sheets.update_respuesta_pregunta(
                    respuesta.id,
                    timeout_prompt_enviado=True,
                )
                sheets.create_respuesta_audit_log(
                    respuesta.id,
                    "timeout_prompt_enviado",
                    {"segundos": inactive_seconds},
                )
    except Exception as e:
        logger.error(f"Error in check_incomplete_respuestas_timeout: {e}", exc_info=True)


# Horas sin actividad antes de recordarle al auditor que dejó una auditoría a
# medias. El cierre definitivo lo marca session.expires_at (24 h).
AUDIT_V2_INACTIVITY_HOURS = 2


def _parse_utc(value: str) -> datetime | None:
    """ISO -> datetime aware en UTC. None si no se puede parsear."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def check_expired_audit_sessions_v2():
    """Sesiones de auditoría v2 (WhatsApp): aviso por inactividad y cierre al vencer.

    La regla es que nada se cierra en silencio: si el auditor deja una auditoría
    a medias se le avisa, y si se vence se le avisa también. Antes de esto el
    campo expires_at existía pero no lo miraba nadie, así que una sesión trabada
    quedaba viva hasta el siguiente redeploy.
    """
    try:
        from audit_session import get_all_sessions, delete_session, save_session

        sessions = get_all_sessions()
        if not sessions:
            return

        meta_client = MetaClient()
        now = datetime.now(timezone.utc)

        for session in sessions:
            try:
                bloques_hechos = len(session.bloques)
                sucursal = session.sucursal_id or "sin sucursal"

                if session.is_expired():
                    await meta_client.send_text(
                        session.telefono,
                        f"⏰ Cerré la auditoría de *{sucursal}* que quedó sin terminar "
                        f"(llevaba {bloques_hechos} de 4 bloques).\n\n"
                        "Cuando quieras arrancar de nuevo, escribí *auditoria*.",
                    )
                    delete_session(session.telefono)
                    logger.info(f"Audit v2 session expired and closed: {session.id_sesion}")
                    continue

                if session.inactivity_notice_at:
                    continue

                last = _parse_utc(session.last_message_at)
                if last is None:
                    continue

                if (now - last).total_seconds() < AUDIT_V2_INACTIVITY_HOURS * 3600:
                    continue

                await meta_client.send_text(
                    session.telefono,
                    f"👋 Tenés la auditoría de *{sucursal}* sin terminar "
                    f"({bloques_hechos} de 4 bloques).\n\n"
                    "Respondé para seguir donde quedaste, o escribí *cancelar* para descartarla.",
                )
                session.inactivity_notice_at = now.isoformat()
                save_session(session)
                logger.info(f"Audit v2 inactivity notice sent: {session.id_sesion}")

            except Exception as exc:
                logger.error(
                    f"Error handling audit v2 session {session.id_sesion}: {exc}",
                    exc_info=True,
                )

    except Exception as e:
        logger.error(f"Error in check_expired_audit_sessions_v2: {e}", exc_info=True)


async def check_expired_audit_sessions():
    """Background job: Check for expired audit sessions (15 min timeout)."""
    try:
        sheets = get_sheets()
        expired_sesiones = sheets.get_sesiones_activas_expiradas(timeout_min=15)
        meta_client = MetaClient()

        for sesion in expired_sesiones:
            timestamp_raw = (sesion.timestamp_ultimo_punto or "").strip()
            if not timestamp_raw:
                continue

            try:
                last_update = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid timestamp_ultimo_punto for session {sesion.id_sesion}: {timestamp_raw}")
                continue

            now_utc = datetime.now(timezone.utc)
            now_local = datetime.now()
            if last_update.tzinfo is not None:
                elapsed_minutes = (now_utc - last_update.astimezone(timezone.utc)).total_seconds() / 60
            else:
                # Backward compatibility for existing naive timestamps stored as local time.
                elapsed_minutes = (now_local - last_update).total_seconds() / 60

            checklist = sheets.get_checklist()
            total_puntos = sesion.total_puntos or len(checklist)
            if sesion.punto_actual >= total_puntos or sesion.punto_actual >= len(checklist):
                logger.info(f"Closing stale completed session without notification: {sesion.id_sesion}")
                sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado="completa",
                    timestamp_ultimo_punto=now_utc.isoformat(),
                    punto_actual=sesion.punto_actual,
                    omitidos_json=sesion.omitidos_json,
                )
                _last_reminder_sent.pop(sesion.id_sesion, None)
                continue

            if elapsed_minutes >= 60:
                logger.info(f"Closing stale session after inactivity without notification: {sesion.id_sesion}")
                sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado="completa",
                    timestamp_ultimo_punto=now_utc.isoformat(),
                    punto_actual=sesion.punto_actual,
                    omitidos_json=sesion.omitidos_json,
                )
                _last_reminder_sent.pop(sesion.id_sesion, None)
                continue

            # Legacy auto-omit branch kept unreachable by the silent close above.
            if False:
                logger.info(f"Auto-omitting point due to inactivity: {sesion.id_sesion}")
                omitidos = _json_list(sesion.omitidos_json)
                omitidos.append(sesion.punto_actual)
                sesion.punto_actual += 1
                sesion.timestamp_ultimo_punto = now_utc.isoformat()

                # Update session
                sheets.update_sesion(
                    id_sesion=sesion.id_sesion,
                    estado=sesion.estado,
                    timestamp_ultimo_punto=sesion.timestamp_ultimo_punto,
                    punto_actual=sesion.punto_actual,
                    omitidos_json=json.dumps(omitidos),
                )

                # Notify auditor
                await meta_client.send_text(
                    sesion.telefono_auditor,
                    "Punto omitido automáticamente por inactividad (60+ min). Continuando...",
                )

                # Move to next point if not finished
                checklist = sheets.get_checklist()
                if sesion.punto_actual < len(checklist):
                    punto = checklist[sesion.punto_actual]
                    await meta_client.send_text(
                        sesion.telefono_auditor,
                        f"""Punto {punto.punto_orden}/{sesion.total_puntos}:
{punto.area} - {punto.descripcion}

Tu evaluación:""",
                    )
                # Clear reminder tracking for this session
                _last_reminder_sent.pop(sesion.id_sesion, None)
                continue

            # Send reminder only once every 15 minutes (up to 3 reminders)
            reminder_state = _last_reminder_sent.get(sesion.id_sesion)
            last_reminder = reminder_state[0] if reminder_state else None
            reminders_sent = reminder_state[1] if reminder_state else 0

            # Check if reminder is due and we haven't exceeded 3 reminders.
            reminder_due = last_reminder is None or (now_utc - last_reminder).total_seconds() >= 900  # 900 = 15 min

            if reminder_due and reminders_sent < 3:
                reminders_sent += 1
                _last_reminder_sent[sesion.id_sesion] = (now_utc, reminders_sent)
                logger.info(f"Audit session timeout for {sesion.telefono_auditor}: {sesion.id_sesion} (reminder #{reminders_sent})")
                checklist = sheets.get_checklist()
                if sesion.punto_actual < len(checklist):
                    punto = checklist[sesion.punto_actual]
                    await meta_client.send_text(
                        sesion.telefono_auditor,
                        f"""Recordatorio: estás en el punto {punto.punto_orden}/{sesion.total_puntos}.
Mandá tu observación o escribe 'saltar'.""",
                    )

        if expired_sesiones:
            logger.info(f"Checked {len(expired_sesiones)} expired audit sessions")
    except Exception as e:
        logger.error(f"Error in audit timeout check job: {e}")
async def daily_summary_job():
    """Background job: Generate and send daily summary."""
    try:
        settings = get_settings()
        if not settings.coordinador_tel:
            logger.warning("COORDINADOR_TEL not configured")
            return

        # Get today's reports
        # TODO: Implement query to get today's reports from Reportes sheet
        # This would require extending SheetsManager with a method to query by date

        summary = f"""ðŸ“Š **Resumen Diario AuditBot**

Fecha: {datetime.now().strftime('%Y-%m-%d')}

[Resumen en construcciÃ³n]

Para mÃ¡s detalles, consulta la hoja de Reportes."""

        meta_client = MetaClient()
        await meta_client.send_text(settings.coordinador_tel, summary)

        logger.info("Daily summary sent to coordinator")
    except Exception as e:
        logger.error(f"Error in daily summary job: {e}")


async def check_overdue_gestion(notify: bool = True):
    """Background job: mark gestiones past their plazo_fecha as Vencida and notify.

    notify=False is used for one-off backfills of a pre-existing backlog (so we
    don't fire a burst of WhatsApp alerts for deviations that have been overdue
    for months) — the recurring scheduled job always runs with notify=True.
    """
    try:
        db = SupabaseManager()
        overdue = db.get_overdue_gestiones()
        if not overdue:
            return

        settings = get_settings()
        meta_client = MetaClient() if notify else None

        for gestion in overdue:
            id_gestion = gestion.get("id_gestion")
            if not id_gestion:
                continue

            db.update_gestion_fields(id_gestion, {"estado": "Vencida"})

            if not notify:
                continue

            db.create_notifications_for_auditors(id_gestion, tipo="vencimiento_proximo")

            if settings.coordinador_tel:
                try:
                    await meta_client.send_alerta_coordinador(
                        settings.coordinador_tel,
                        gestion.get("sucursal") or gestion.get("id_sucursal") or "",
                        gestion.get("bloque") or "",
                        gestion.get("desvio") or "",
                        gestion.get("severidad") or "Media",
                    )
                except Exception as e:
                    logger.warning(f"Failed to alert coordinator about overdue gestion {id_gestion}: {e}")

        logger.info(f"Marked {len(overdue)} gestion(es) as Vencida (notify={notify})")
    except Exception as e:
        logger.error(f"Error in overdue gestion check job: {e}")


async def remind_sla_auditor_revision():
    """Background job: alert auditor/admin about corrections stuck in En_revision past the
    72h SLA. Uses a bounded lookback window (see get_gestiones_en_revision_stale) so each
    gestion is alerted once instead of every run."""
    try:
        db = SupabaseManager()
        stale = db.get_gestiones_en_revision_stale(hours_min=72, hours_max=73)
        if not stale:
            return

        for gestion in stale:
            id_gestion = gestion.get("id_gestion")
            if not id_gestion:
                continue
            db.create_notifications_for_auditors(id_gestion, tipo="sla_revision_vencido")

        logger.info(f"SLA reminder: {len(stale)} gestion(es) en revision hace mas de 72h")

        if settings.coordinador_tel:
            meta_client = MetaClient()
            for gestion in stale:
                try:
                    await meta_client.send_text(
                        settings.coordinador_tel,
                        f"FarmaAudit: el desvio {gestion.get('id_gestion')} ({gestion.get('sucursal')}) "
                        "lleva mas de 72hs esperando revision del auditor.",
                    )
                except Exception as exc:
                    logger.warning(f"Failed to alert coordinator about stale review {gestion.get('id_gestion')}: {exc}")
    except Exception as e:
        logger.error(f"Error in overdue gestion check job: {e}", exc_info=True)


RECORDATORIO_COOLDOWN_HORAS = 24


async def _enviar_recordatorio_sucursal(
    db: SupabaseManager,
    meta_client: MetaClient,
    id_sucursal: str,
    group: Dict[str, Any],
    canal: str,
    enviado_por: Optional[str] = None,
) -> Dict[str, Any]:
    """Un solo camino para mandar el recordatorio de desvíos pendientes de una
    sucursal — lo usan el botón manual y el job automático de cada 3 días, así
    no divergen ni pisan el cooldown del otro. Registra siempre en
    recordatorios_sucursal, incluso cuando no llega a enviar nada: es la única
    forma de que "el job falla en silencio" deje de ser cierto.

    No manda plantilla fuera de la ventana de 24h: farmaaudit_novedades sigue
    sin aprobar en Meta, y un envío que falla la mayoría de las veces es peor
    que no ofrecer el botón (ver ARQUITECTURA_PANEL_DESVIOS.md §4.5).
    """
    cantidad = group["cantidad"]
    dias = group["dias_abierto_max"]
    sucursales = ", ".join(group["sucursales"]) or "tu sucursal"

    responsable = resolve_responsable_by_sucursal(id_sucursal)
    if not responsable or not responsable.telefono:
        db.registrar_recordatorio_sucursal(
            id_sucursal, canal, "sin_encargado", enviado_por=enviado_por, cantidad_desvios=cantidad
        )
        return {"resultado": "sin_encargado"}

    ultimo = db.get_ultimo_recordatorio_enviado(id_sucursal)
    if ultimo and ultimo.get("enviado_at"):
        enviado_at = datetime.fromisoformat(ultimo["enviado_at"].replace("Z", "+00:00"))
        proximo = enviado_at + timedelta(hours=RECORDATORIO_COOLDOWN_HORAS)
        if datetime.now(timezone.utc) < proximo:
            return {"resultado": "cooldown", "proximo_disponible_at": proximo.isoformat()}

    if not ventana_abierta(responsable):
        db.registrar_recordatorio_sucursal(
            id_sucursal, canal, "sin_ventana", enviado_por=enviado_por,
            detalle=f"ultimo_mensaje_entrante_at={responsable.ultimo_mensaje_entrante_at}",
            cantidad_desvios=cantidad,
        )
        return {"resultado": "sin_ventana", "ultimo_mensaje": responsable.ultimo_mensaje_entrante_at}

    texto = (
        f"🔔 Recordatorio: tenés {cantidad} desvío(s) pendientes de resolver "
        f"en {sucursales}, el más antiguo desde hace {dias} días.\n\n"
        f"Escribinos a este mismo número a medida que los vayas gestionando."
    )
    try:
        ok = await meta_client.send_text(responsable.telefono, texto)
    except Exception as exc:
        logger.warning(f"Error sending recordatorio to {responsable.telefono}: {exc}")
        ok = False

    resultado = "enviado" if ok else "fallido"
    db.registrar_recordatorio_sucursal(
        id_sucursal, canal, resultado, enviado_por=enviado_por, cantidad_desvios=cantidad
    )
    return {"resultado": resultado}


async def remind_responsable_desvios_pendientes():
    """Background job: recurring reminder to branch managers who still have open
    desvios, on top of the one-time notice sent right when the audit finds them
    (see _notify_responsable_desvios_pendientes in audit_handlers.py). Runs once
    a day; a manager gets pinged again every N days for as long as something
    stays open (see get_gestiones_pendientes_recordatorio)."""
    try:
        db = SupabaseManager()
        due = db.get_gestiones_pendientes_recordatorio(intervalo_dias=3)
        if not due:
            return

        meta_client = MetaClient()
        for group in due:
            resultado = await _enviar_recordatorio_sucursal(
                db, meta_client, group["id_sucursal"], group, canal="bot", enviado_por=None
            )
            if resultado["resultado"] not in ("enviado",):
                logger.warning(f"Recordatorio automatico para {group['id_sucursal']}: {resultado['resultado']}")

        logger.info(f"Pending-desvios reminder processed for {len(due)} branch(es)")
    except Exception as e:
        logger.error(f"Error in responsable reminder job: {e}", exc_info=True)


async def regenerate_thumbnails_job():
    """Background job: Regenerate missing thumbnails for existing evidences."""
    try:
        supabase_mgr = SupabaseManager()
        result = supabase_mgr.regenerate_missing_thumbnails()
        logger.info(f"Thumbnail regeneration completed: {result}")
    except Exception as e:
        logger.error(f"Error in thumbnail regeneration job: {e}", exc_info=True)


@app.post("/admin/thumbnails/regenerate")
async def regenerate_thumbnails_endpoint(request: Request):
    """Manual endpoint to regenerate missing thumbnails. Requires admin role."""
    await _require_admin(request)
    try:
        supabase_mgr = SupabaseManager()
        result = supabase_mgr.regenerate_missing_thumbnails()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Error regenerating thumbnails: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


# ============== AUDIT FICHES ENDPOINTS ==============

from audit_fiches_manager import AuditFichesManager
from audit_pdf_generator import generate_controles_summary_pdf
from fastapi import Query
from typing import Optional


async def _with_fresh_pdf_url(ficha: dict) -> dict:
    """Replace a ficha's stored (private) Storage path with a fresh,
    short-lived signed URL, minted on demand for this authenticated request.
    """
    # NOTE: google_drive_id predates the Supabase Storage migration; it now
    # holds the Storage object path for this ficha's PDF.
    storage_path = ficha.get("google_drive_id")
    if storage_path:
        fresh_url = SupabaseManager().create_signed_ficha_url(storage_path)
        if fresh_url:
            ficha = {**ficha, "url_pdf": fresh_url}
    return ficha


@app.get("/api/audit-fiches/list")
async def get_audit_fiches(
    request: Request,
    sucursal_id: Optional[str] = Query(None),
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
    auditor_nombre: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get audit fiches with optional filters."""
    await _require_admin_or_auditor(request)
    try:
        fiches = await AuditFichesManager.get_fiches(
            sucursal_id=sucursal_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            auditor_nombre=auditor_nombre,
            limit=limit,
            offset=offset,
        )
        fiches = [await _with_fresh_pdf_url(f) for f in fiches]
        return {
            "status": "ok",
            "count": len(fiches),
            "data": fiches,
            "filters": {
                "sucursal_id": sucursal_id,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "auditor_nombre": auditor_nombre,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching fiches: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@app.get("/api/audit-fiches/export-pdf")
async def export_audit_fiches_pdf(
    request: Request,
    sucursal_id: Optional[str] = Query(None),
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    """Export a summary PDF of all audit controls performed, with links to full fichas."""
    await _require_admin_or_auditor(request)
    try:
        db = SupabaseManager()
        sesiones = db.get_auditoria_sesiones_historicas(
            sucursal_id=sucursal_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
        )
        fiches = await AuditFichesManager.get_fiches(
            sucursal_id=sucursal_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, limit=1000
        )
        fiches = [await _with_fresh_pdf_url(f) for f in fiches]

        sucursales_by_id = {s.id: s.nombre for s in db.get_all_sucursales()}
        auditores_by_tel = {a.telefono: a.nombre for a in db.get_all_auditores()}

        pdf_bytes = generate_controles_summary_pdf(
            sesiones=sesiones,
            fichas=fiches,
            sucursales_by_id=sucursales_by_id,
            auditores_by_tel=auditores_by_tel,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

        filename = f"FarmaAudit_Controles_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting controles PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@app.get("/api/audit-fiches/sucursales")
async def get_audit_fiches_sucursales(request: Request):
    """Get list of sucursales with audit fiches."""
    await _require_admin_or_auditor(request)
    try:
        sucursales = await AuditFichesManager.get_sucursales_with_fiches()
        unique_sucursales = []
        seen = set()
        for item in sucursales:
            sid = item.get("sucursal_id")
            if sid and sid not in seen:
                unique_sucursales.append(sid)
                seen.add(sid)
        return {"status": "ok", "count": len(unique_sucursales), "data": unique_sucursales}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sucursales: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@app.get("/api/audit-fiches/{ficha_id}")
async def get_audit_ficha(ficha_id: str, request: Request):
    """Get details of specific audit ficha."""
    await _require_admin_or_auditor(request)
    try:
        db = SupabaseManager()
        response = db.client.table("audit_fiches").select("*").eq("id", ficha_id).single().execute()
        if response.data:
            return {"status": "ok", "data": await _with_fresh_pdf_url(response.data)}
        raise HTTPException(status_code=404, detail="Ficha not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching ficha: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@app.post("/api/analisis/ficha/{ficha_id}")
async def analizar_ficha(ficha_id: str, request: Request):
    """Run multi-agent analysis on a completed audit ficha.

    Executes 5 specialized Claude agents in parallel (field auditor, quality
    analyst, Argentine perfumery expert, ANMAT regulatory advisor, business
    analyst) then synthesizes the results into an executive action plan.
    """
    await _require_admin_or_auditor(request)
    try:
        from analysis_agents import AuditAnalysisOrchestrator
        result = await AuditAnalysisOrchestrator().analizar(ficha_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running audit analysis for ficha {ficha_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error al ejecutar el análisis")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
