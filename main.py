"""FastAPI application for AuditBot webhook and background jobs."""

import logging
from datetime import datetime, timedelta, timezone
import json
import asyncio
import uuid
from collections import OrderedDict

from fastapi import FastAPI, Request, HTTPException
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


class BloqueScore(BaseModel):
    id: str
    nombre: str
    puntuacion: int  # 1-5


class DesvioItem(BaseModel):
    id: str
    bloque: str
    descripcion: str
    foto_url: str | None = None


class AuditoriaCompletadaPerfumeriaRequest(BaseModel):
    id_sesion: str
    sucursal_id: str
    sucursal_nombre: str
    auditor_nombre: str
    auditor_telefono: str
    bloques_scores: list[BloqueScore]
    desvios: list[DesvioItem] = []

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
async def send_encargado_notification(payload: EncargadoNotificationRequest):
    """Send a WhatsApp notification to the branch manager for one deviation."""
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

    actor_id = payload.actor_id or profile["id"]
    actor_nombre = payload.actor_nombre or profile.get("nombre") or "Usuario"
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


@app.post("/api/auditorias-completadas/perfumeria")
async def create_perfumeria_deviations(payload: AuditoriaCompletadaPerfumeriaRequest, request: Request):
    """Receive completed perfumery audit from frontend and create Gestion records."""
    profile = await _require_admin_or_auditor(request)
    client = _get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        now = datetime.now(timezone.utc).isoformat()
        created_gestiones = []

        # Get sucursal info to find responsable contact
        sucursal_response = (
            client.table("sucursales")
            .select("responsable, tel_responsable, zona")
            .eq("id", payload.sucursal_id)
            .maybe_single()
            .execute()
        )
        sucursal_info = sucursal_response.data or {}
        responsable = sucursal_info.get("responsable", "")
        tel_responsable = sucursal_info.get("tel_responsable", "")

        for desvio in payload.desvios:
            # Create Reporte record
            reporte_record = {
                "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "hora": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "cuadrilla": "",  # Not applicable for perfumery audits
                "auditor": payload.auditor_nombre,
                "id_sucursal": payload.sucursal_id,
                "sucursal": payload.sucursal_nombre,
                "area": desvio.bloque,  # Map bloque to area
                "subitem": "",  # Not applicable for free-form perfumery audits
                "descripcion": desvio.descripcion,
                "severidad": "Media",  # Default severity, could be parameterized later
                "foto_url": desvio.foto_url,
                "creado_por_audio": False,
                "timestamp": now,
            }

            reporte_response = (
                client.table("reportes")
                .insert(reporte_record)
                .execute()
            )

            if not reporte_response.data:
                logger.error(f"Failed to create reporte for desvio {desvio.id}")
                continue

            reporte_id = reporte_response.data[0]["id"]

            # Create Gestion record
            gestion_record = {
                "id_reporte": reporte_id,
                "id_sucursal": payload.sucursal_id,
                "sucursal": payload.sucursal_nombre,
                "desvio": desvio.descripcion,
                "severidad": "Media",
                "responsable": responsable,
                "tel_responsable": tel_responsable,
                "plazo_fecha": (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"),
                "plan_accion": "",  # Empty initially, responsable fills it
                "estado": "Abierta",
                "created_at": now,
                "updated_at": now,
            }

            gestion_response = (
                client.table("gestiones")
                .insert(gestion_record)
                .execute()
            )

            if not gestion_response.data:
                logger.error(f"Failed to create gestion for reporte {reporte_id}")
                continue

            gestion_id = gestion_response.data[0]["id_gestion"]
            created_gestiones.append(gestion_response.data[0])

            # Create initial DesvioEvento for creation
            evento_record = {
                "id_gestion": gestion_id,
                "tipo": "creacion",
                "comentario": f"Desvío detectado en auditoría perfumería - Bloque: {desvio.bloque}",
                "actor_nombre": payload.auditor_nombre,
                "actor_id": payload.auditor_telefono,
                "metadata": {
                    "bloque": desvio.bloque,
                    "foto_url": desvio.foto_url,
                    "id_sesion": payload.id_sesion,
                },
                "created_at": now,
            }

            evento_response = (
                client.table("desvio_eventos")
                .insert(evento_record)
                .execute()
            )

            if not evento_response.data:
                logger.warning(f"Failed to create evento for gestion {gestion_id}")

        # Notify responsable about deviations if phone number exists
        if tel_responsable and created_gestiones:
            normalized_tel = "".join(ch for ch in tel_responsable if ch.isdigit())
            if normalized_tel:
                deviation_count = len(created_gestiones)

                message = (
                    f"FarmaAudit: Se detectaron {deviation_count} desvío(s) en {payload.sucursal_nombre}\n\n"
                    f"Auditor: {payload.auditor_nombre}\n\n"
                    "Responde este WhatsApp para gestionar los desvíos encontrados."
                )

                meta_client = MetaClient()
                sent = await meta_client.send_text(normalized_tel, message)
                if not sent:
                    logger.warning(f"Failed to notify responsable {normalized_tel} about deviations")

        logger.info(
            f"Created {len(created_gestiones)} gestiones for audit {payload.id_sesion} "
            f"in sucursal {payload.sucursal_id}"
        )
        return {"status": "ok", "deviations_created": len(created_gestiones)}

    except Exception as exc:
        logger.error(f"Failed to create perfumeria gestiones: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudieron crear los desvíos")


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


@app.post("/webhook")
async def webhook(request: Request):
    """Meta WhatsApp Cloud API webhook entry point."""
    correlation_id = str(uuid.uuid4())[:8]  # Short correlation ID for logs
    message_id = ""
    message_claimed = False
    processed_successfully = False
    try:
        data = await request.json()

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

        # NEW: Try perfumery audit v2 first if user has active session
        session = get_session(payload.telefono)
        if session and session.estado != AuditState.DONE:
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


async def regenerate_thumbnails_job():
    """Background job: Regenerate missing thumbnails for existing evidences."""
    try:
        supabase_mgr = SupabaseManager()
        result = supabase_mgr.regenerate_missing_thumbnails()
        logger.info(f"Thumbnail regeneration completed: {result}")
    except Exception as e:
        logger.error(f"Error in thumbnail regeneration job: {e}", exc_info=True)


@app.post("/admin/thumbnails/regenerate")
async def regenerate_thumbnails_endpoint():
    """
    Manual endpoint to regenerate missing thumbnails.
    Protected: requires admin context (implement auth check if needed).
    """
    try:
        supabase_mgr = SupabaseManager()
        result = supabase_mgr.regenerate_missing_thumbnails()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Error regenerating thumbnails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== AUDIT FICHES ENDPOINTS ==============

from audit_fiches_manager import AuditFichesManager
from fastapi import Query
from typing import Optional


@app.get("/api/audit-fiches/list")
async def get_audit_fiches(
    sucursal_id: Optional[str] = Query(None),
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
    auditor_nombre: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get audit fiches with optional filters."""

    try:
        fiches = await AuditFichesManager.get_fiches(
            sucursal_id=sucursal_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            auditor_nombre=auditor_nombre,
            limit=limit,
            offset=offset,
        )

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

    except Exception as e:
        logger.error(f"Error fetching fiches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit-fiches/sucursales")
async def get_audit_fiches_sucursales():
    """Get list of sucursales with audit fiches."""

    try:
        sucursales = await AuditFichesManager.get_sucursales_with_fiches()

        # Extract unique sucursal_ids
        unique_sucursales = []
        seen = set()
        for item in sucursales:
            sucursal_id = item.get("sucursal_id")
            if sucursal_id and sucursal_id not in seen:
                unique_sucursales.append(sucursal_id)
                seen.add(sucursal_id)

        return {
            "status": "ok",
            "count": len(unique_sucursales),
            "data": unique_sucursales,
        }

    except Exception as e:
        logger.error(f"Error fetching sucursales: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit-fiches/{ficha_id}")
async def get_audit_ficha(ficha_id: str):
    """Get details of specific audit ficha."""

    try:
        db = SupabaseManager()
        response = db.client.table("audit_fiches").select("*").eq("id", ficha_id).single().execute()

        if response.data:
            return {
                "status": "ok",
                "data": response.data,
            }
        else:
            raise HTTPException(status_code=404, detail="Ficha not found")

    except Exception as e:
        logger.error(f"Error fetching ficha: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
