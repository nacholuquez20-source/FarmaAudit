"""Contextual per-branch assistant.

Explains a sucursal's current state in plain language and suggests next
actions, using only data already shown on SucursalDetail (no free chat, no
cross-session memory, no capacity to take actions — WhatsApp still does
that). Single Claude call, deliberately lighter than
AuditAnalysisOrchestrator's 5-agent ficha analysis (analysis_agents.py),
which this mirrors for the client/call pattern.

Call SucursalAssistant().explicar(id_sucursal).
"""

import json
import logging
import time
from typing import Any, Dict, Optional

from anthropic import AsyncAnthropic

from config import get_settings
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_CACHE_TTL_SECONDS = 24 * 60 * 60  # Un dia: no repagar el call en cada render de la ficha.


def _strip_md(text: str) -> str:
    """Remove markdown code fences if Claude wraps JSON in them."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


_SYSTEM_PROMPT = """Sos un asistente que ayuda a un administrador o auditor de farmacias a
entender rápido el estado de una sucursal, en lenguaje simple y sin jerga
técnica. Te paso datos ya calculados de esa sucursal — nunca inventes
números que no te dieron ni sugieras nada fuera de esos datos.

Devolvé SOLO un JSON con esta forma exacta, sin texto extra:
{
  "resumen": "1-2 oraciones explicando el estado general en lenguaje simple",
  "por_que": "1-2 oraciones explicando por qué está en ese estado, citando los datos concretos que te pasaron",
  "acciones": [{"texto": "acción concreta y corta", "prioridad": "alta"|"media"|"baja"}]
}

Máximo 3 acciones, ordenadas por prioridad. Si la sucursal está bien y no
hace falta hacer nada, "acciones" va vacío y el resumen lo dice."""


class SucursalAssistant:
    # Cache de proceso, no de instancia (se instancia una por request) — clave
    # id_sucursal, valor (timestamp, resultado). Mismo motivo que roadmap
    # B8/W6: no volver a pagar el call de Claude en cada carga de pantalla.
    _cache: Dict[str, tuple] = {}

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None
        self._db = SupabaseManager()

    def _client_(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    def _contexto(self, id_sucursal: str) -> Optional[Dict[str, Any]]:
        """Mismos datos que ya renderiza SucursalDetail — el asistente no
        consulta nada que el usuario no esté viendo en pantalla."""
        resumen = self._db.get_resumen_sucursales()
        row = next((r for r in resumen if r.get("id") == id_sucursal), None)
        if not row:
            return None
        return {
            "nombre": row.get("nombre"),
            "estado_salud": row.get("estado_salud"),
            "ultimo_score": row.get("ultimo_score"),
            "dias_desde_auditoria": row.get("dias_desde_auditoria"),
            "desvios_abiertos": row.get("desvios_abiertos"),
            "desvios_vencidos": row.get("desvios_vencidos"),
            "desvios_para_revisar": row.get("desvios_para_revisar"),
            "dias_sin_accion_encargado": row.get("dias_sin_accion"),
            "tiene_encargado_con_telefono": bool(row.get("responsable") and row.get("tel_responsable")),
            "desvios_por_bloque_y_severidad": row.get("categorias", {}),
        }

    async def explicar(self, id_sucursal: str) -> Dict[str, Any]:
        cached = self._cache.get(id_sucursal)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        contexto = self._contexto(id_sucursal)
        if contexto is None:
            return {"error": "sucursal_no_encontrada"}

        try:
            resp = await self._client_().messages.create(
                model=_MODEL,
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(contexto, ensure_ascii=False)}],
            )
            result = json.loads(_strip_md(resp.content[0].text))
        except json.JSONDecodeError:
            logger.warning(f"Asistente de sucursal {id_sucursal}: respuesta no-JSON de Claude")
            return {"error": "parse_error"}
        except Exception as exc:
            logger.error(f"Asistente de sucursal {id_sucursal} fallo: {exc}")
            return {"error": str(exc)}

        self._cache[id_sucursal] = (time.time(), result)
        return result
