"""Multi-agent analysis system for completed pharmacy audits.

Runs 5 specialized Claude agents in parallel then synthesizes into an
executive action plan. Call AuditAnalysisOrchestrator.analizar(ficha_id).
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from anthropic import AsyncAnthropic

from config import get_settings
from supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"


# ─── helpers ────────────────────────────────────────────────────────────────

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


# ─── orchestrator ───────────────────────────────────────────────────────────

class AuditAnalysisOrchestrator:
    """Orchestrates 5 specialized agents to analyse a completed audit ficha."""

    def __init__(self):
        self._client: AsyncAnthropic | None = None
        self._db = SupabaseManager()

    def _client_(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    # ── Claude call ─────────────────────────────────────────────────────────

    async def _call(self, system: str, user: str) -> dict:
        try:
            resp = await self._client_().messages.create(
                model=_MODEL,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = _strip_md(resp.content[0].text)
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Agent returned non-JSON — returning raw excerpt")
            return {"error": "parse_error"}
        except Exception as exc:
            logger.error("Agent call failed: %s", exc)
            return {"error": str(exc)}

    # ── data fetching ────────────────────────────────────────────────────────

    def _fetch(self, ficha_id: str) -> tuple[dict, list[dict], list[dict]]:
        """Return (ficha, gestiones_del_dia, historico_sucursal)."""
        db = self._db

        ficha_resp = db.client.table("audit_fiches").select("*").eq("id", ficha_id).limit(1).execute()
        if not ficha_resp.data:
            return {}, [], []
        ficha = ficha_resp.data[0]

        # Gestiones created on the same calendar day as the ficha.
        # Se usa un límite superior EXCLUSIVo del día siguiente (< dia+1) en vez
        # de "23:59:59", para no perder desvíos con fracción de segundo en el
        # último segundo del día.
        dia = (ficha.get("fecha_auditoria") or ficha.get("created_at") or "")[:10]
        gestiones: list[dict] = []
        if dia and ficha.get("sucursal_id"):
            try:
                dia_sig = (datetime.fromisoformat(dia) + timedelta(days=1)).date().isoformat()
            except ValueError:
                dia_sig = None
            query = (
                db.client.table("gestion")
                .select("id_gestion,desvio,severidad,responsable,plazo_fecha,plan_accion,estado,area")
                .eq("id_sucursal", ficha["sucursal_id"])
                .gte("created_at", f"{dia}T00:00:00")
            )
            if dia_sig:
                query = query.lt("created_at", f"{dia_sig}T00:00:00")
            g_resp = query.order("created_at").execute()
            gestiones = g_resp.data or []

        # Last 5 fichas for the same sucursal (historical context)
        historico: list[dict] = []
        if ficha.get("sucursal_id"):
            h_resp = (
                db.client.table("audit_fiches")
                # audit_fiches no guarda scores por bloque: solo el promedio.
                .select("fecha_auditoria,puntuacion_promedio,desvios_count")
                .eq("sucursal_id", ficha["sucursal_id"])
                .neq("id", ficha_id)
                .order("fecha_auditoria", desc=True)
                .limit(5)
                .execute()
            )
            historico = h_resp.data or []

        return ficha, gestiones, historico

    # ── agent 1: campo ───────────────────────────────────────────────────────

    _SYS_CAMPO = """Sos un auditor de campo experto en farmacias argentinas con 15 años de experiencia.
Analizás los resultados de una auditoría completada y producís un diagnóstico claro y objetivo.

Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni texto extra:
{
  "resumen_ejecutivo": "2-3 oraciones sobre el estado general",
  "bloques_criticos": ["bloque"],
  "bloques_destacados": ["bloque"],
  "calidad_evidencia": "alta|media|baja",
  "diagnostico_general": "positivo|regular|critico"
}"""

    async def _agente_campo(self, ficha: dict, gestiones: list[dict]) -> dict:
        user = (
            f"AUDITORÍA\n"
            f"Sucursal: {ficha.get('sucursal_id')} | Auditor: {ficha.get('auditor_nombre')} | "
            f"Fecha: {ficha.get('fecha_auditoria')}\n\n"
            f"SCORES\n"
            f"Promedio: {ficha.get('puntuacion_promedio')}/5\n\n"
            f"EVIDENCIA\nDesvíos: {ficha.get('desvios_count')} | Fotos: {ficha.get('fotos_count')}\n\n"
            f"DESVÍOS ENCONTRADOS\n{json.dumps(gestiones[:20], ensure_ascii=False)}"
        )
        return await self._call(self._SYS_CAMPO, user)

    # ── agent 2: calidad / tendencias ────────────────────────────────────────

    _SYS_CALIDAD = """Sos analista de calidad senior en una cadena de farmacias argentinas.
Identificás tendencias, reincidencias y patrones en el historial de auditorías de cada sucursal.

Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni texto extra:
{
  "tendencia_general": "mejorando|estable|deteriorando",
  "variacion_score_vs_anterior": null,
  "desvios_reincidentes": ["descripción"],
  "bloques_mejorando": ["bloque"],
  "bloques_deteriorando": ["bloque"],
  "nivel_riesgo_historico": "bajo|medio|alto|critico",
  "recomendacion_frecuencia_auditoria": "quincenal|mensual|bimestral"
}"""

    async def _agente_calidad(self, ficha: dict, historico: list[dict]) -> dict:
        def fmt(h: dict) -> dict:
            return {
                "fecha": h.get("fecha_auditoria"),
                "promedio": h.get("puntuacion_promedio"),
                "desvios": h.get("desvios_count"),
            }

        user = (
            f"AUDITORÍA ACTUAL\n"
            f"Score promedio: {ficha.get('puntuacion_promedio')} | "
            f"Desvíos: {ficha.get('desvios_count')}\n\n"
            f"HISTORIAL (más reciente primero)\n"
            f"{json.dumps([fmt(h) for h in historico], ensure_ascii=False)}"
        )
        return await self._call(self._SYS_CALIDAD, user)

    # ── agent 3: perfumería argentina ────────────────────────────────────────

    _SYS_PERFUMERIA = """Sos especialista en perfumería y cosmética en retail farmacéutico argentino.
Conocés en profundidad acuerdos de exhibición, planogramas y requisitos comerciales de marcas presentes
en farmacias argentinas: Natura, Avon, L'Bel, Caro Cuore, Yanbal, Revlon, L'Oréal, Maybelline, Dove,
Rexona, Pantene, Elvive, Votre Peau, Neutrogena, Nivea, Noxzema, entre otras.

Analizás desvíos en la sección de perfumería y evaluás el riesgo para acuerdos comerciales con marcas.

Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni texto extra:
{
  "marcas_potencialmente_afectadas": ["marca"],
  "riesgo_acuerdo_comercial": "bajo|medio|alto",
  "desvios_criticos_perfumeria": ["descripción"],
  "impacto_exhibicion": "descripción del impacto",
  "acciones_urgentes": ["acción concreta"],
  "planograma_comprometido": true
}"""

    async def _agente_perfumeria(self, gestiones: list[dict]) -> dict:
        kw = {"perfum", "cosmet", "marca", "exhib", "planograma", "burb", "promo", "ofer", "fragran", "colonia"}
        relevantes = [
            g for g in gestiones
            if any(k in (str(g.get("desvio", "")) + str(g.get("area", ""))).lower() for k in kw)
        ]
        user = (
            f"DESVÍOS SECCIÓN PERFUMERÍA/COSMÉTICA/EXHIBICIÓN:\n"
            f"{json.dumps(relevantes or gestiones[:15], ensure_ascii=False)}\n\n"
            f"Evaluá el impacto sobre acuerdos comerciales con marcas de perfumería argentina."
        )
        return await self._call(self._SYS_PERFUMERIA, user)

    # ── agent 4: normativo / ANMAT ───────────────────────────────────────────

    _SYS_NORMATIVO = """Sos farmacéutico matriculado con especialización en regulación ANMAT
y buenas prácticas de farmacia (BPF) en Argentina.
Evaluás desvíos de auditoría y determinás el riesgo regulatorio.

Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni texto extra:
{
  "nivel_alerta_anmat": "verde|amarillo|naranja|rojo",
  "desvios_con_riesgo_regulatorio": ["descripción"],
  "areas_riesgo": ["area"],
  "recomendacion_normativa": "acciones regulatorias recomendadas",
  "requiere_accion_inmediata": false,
  "plazo_regularizacion_max_dias": 30
}"""

    async def _agente_normativo(self, gestiones: list[dict]) -> dict:
        criticos = [g for g in gestiones if g.get("severidad") == "Alta"]
        user = (
            f"DESVÍOS DE AUDITORÍA (severidad Alta primero):\n"
            f"{json.dumps((criticos + gestiones)[:20], ensure_ascii=False)}\n\n"
            f"Evaluá desde perspectiva regulatoria ANMAT y buenas prácticas de farmacia Argentina."
        )
        return await self._call(self._SYS_NORMATIVO, user)

    # ── agent 5: modelo de negocio ───────────────────────────────────────────

    _SYS_NEGOCIO = """Sos analista de negocios especializado en retail farmacéutico argentino.
Evaluás el impacto económico de desvíos encontrados en auditorías de perfumería y cosmética.

Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni texto extra:
{
  "score_salud_negocio": 75,
  "riesgo_perdida_ventas": "bajo|medio|alto|critico",
  "desvios_mayor_impacto_economico": ["descripción"],
  "prioridades": [
    {"desvio": "descripción", "prioridad": 1, "impacto": "alto|medio|bajo", "plazo_dias": 7}
  ],
  "inversion_requerida": "baja|media|alta",
  "retorno_esperado": "descripción breve del beneficio de corregir"
}"""

    async def _agente_negocio(self, ficha: dict, gestiones: list[dict]) -> dict:
        alta = sum(1 for g in gestiones if g.get("severidad") == "Alta")
        media = sum(1 for g in gestiones if g.get("severidad") == "Media")
        baja = sum(1 for g in gestiones if g.get("severidad") == "Baja")
        user = (
            f"AUDITORÍA\n"
            f"Score promedio: {ficha.get('puntuacion_promedio')}/5 | "
            f"Desvíos totales: {ficha.get('desvios_count')} "
            f"(Alta: {alta} | Media: {media} | Baja: {baja})\n\n"
            f"DESVÍOS:\n{json.dumps(gestiones[:20], ensure_ascii=False)}\n\n"
            f"Evaluá impacto en ventas y ROI de correcciones para una farmacia mediana argentina."
        )
        return await self._call(self._SYS_NEGOCIO, user)

    # ── synthesis ────────────────────────────────────────────────────────────

    _SYS_SINTESIS = """Sos el director de calidad de una cadena de farmacias argentinas.
Recibís el análisis de 5 especialistas sobre la misma auditoría y sintetizás en un plan ejecutivo claro.

Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni texto extra:
{
  "diagnostico_integral": "2-3 oraciones ejecutivas del estado de la sucursal",
  "nivel_urgencia": "normal|urgente|critico",
  "score_riesgo_global": 42,
  "top_3_acciones_inmediatas": ["acción 1", "acción 2", "acción 3"],
  "proxima_auditoria_en_dias": 30,
  "mensaje_para_encargado": "Mensaje directo al encargado de sucursal. Tono profesional y accesible. Máx 3 párrafos."
}"""

    async def _sintetizar(self, agentes: dict) -> dict:
        user = (
            f"ANÁLISIS DE 5 ESPECIALISTAS:\n\n"
            f"AUDITOR DE CAMPO:\n{json.dumps(agentes.get('campo', {}), ensure_ascii=False)}\n\n"
            f"ANALISTA DE CALIDAD (tendencias históricas):\n{json.dumps(agentes.get('calidad', {}), ensure_ascii=False)}\n\n"
            f"ESPECIALISTA PERFUMERÍA ARGENTINA:\n{json.dumps(agentes.get('perfumeria', {}), ensure_ascii=False)}\n\n"
            f"FARMACÉUTICO / NORMATIVO ANMAT:\n{json.dumps(agentes.get('normativo', {}), ensure_ascii=False)}\n\n"
            f"ANALISTA DE NEGOCIO:\n{json.dumps(agentes.get('negocio', {}), ensure_ascii=False)}\n\n"
            f"Sintetizá en un diagnóstico ejecutivo y plan de acción prioritario."
        )
        return await self._call(self._SYS_SINTESIS, user)

    # ── public API ───────────────────────────────────────────────────────────

    async def analizar(self, ficha_id: str) -> dict:
        """Run all 5 agents in parallel, synthesize, and return the full report."""
        ficha, gestiones, historico = self._fetch(ficha_id)
        if not ficha:
            return {"error": f"Ficha {ficha_id!r} no encontrada"}

        # 5 agents in parallel
        results = await asyncio.gather(
            self._agente_campo(ficha, gestiones),
            self._agente_calidad(ficha, historico),
            self._agente_perfumeria(gestiones),
            self._agente_normativo(gestiones),
            self._agente_negocio(ficha, gestiones),
            return_exceptions=True,
        )

        def safe(r):
            return r if not isinstance(r, Exception) else {"error": str(r)}

        agentes = {
            "campo":      safe(results[0]),
            "calidad":    safe(results[1]),
            "perfumeria": safe(results[2]),
            "normativo":  safe(results[3]),
            "negocio":    safe(results[4]),
        }

        # Si TODOS los agentes fallaron, no sintetizamos sobre basura: sería un
        # plan ejecutivo aparentemente válido construido sobre errores.
        if all(isinstance(a, dict) and "error" in a for a in agentes.values()):
            logger.error("Todos los agentes fallaron para ficha %s — se omite la síntesis", ficha_id)
            sintesis = {"error": "analysis_failed", "diagnostico_integral": "No se pudo completar el análisis. Reintentá."}
        else:
            sintesis = await self._sintetizar(agentes)

        return {
            "ficha_id":        ficha_id,
            "sucursal_id":     ficha.get("sucursal_id"),
            "fecha_auditoria": ficha.get("fecha_auditoria"),
            "agentes":         agentes,
            "sintesis":        sintesis,
            "generado_en":     datetime.now(timezone.utc).isoformat(),
        }
