"""Claude API parser for audit findings."""

import json
import logging
from typing import Optional

from anthropic import AsyncAnthropic

from config import get_settings
from models import (
    ParserResponse, Hallazgo, Severidad, ChecklistPunto, PuntoEvalResult,
    ItemBloque, ResultadoItem, StockItem, DesvioLibre
)
from sheets import SheetsManager

logger = logging.getLogger(__name__)


class AuditParser:
    """Parser using Claude API for audit findings."""

    def __init__(self):
        """Initialize Claude API client."""
        settings = get_settings()
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
        self.sheets = SheetsManager()
        logger.info(f"AuditParser initialized with model {self.model}")

    def _build_system_prompt(self) -> str:
        """Build system prompt with facility and area catalogs."""
        try:
            sucursales = self.sheets.get_all_sucursales()
            areas = self.sheets.get_all_areas()

            sucursales_json = json.dumps(
                [vars(s) for s in sucursales],
                indent=2,
                ensure_ascii=False,
            )
            areas_json = json.dumps(
                [{"area": a.area, "subitems": a.subitems} for a in areas],
                indent=2,
                ensure_ascii=False,
            )

            return f"""Eres un especialista en auditoría de calidad para farmacias.
Tu tarea es analizar mensajes de auditores y extraer hallazgos específicos.

## SUCURSALES DISPONIBLES:
{sucursales_json}

## CATÁLOGO DE ÁREAS Y SUB-ITEMS:
{areas_json}

## REGLAS DE SEVERIDAD:
- ALTA: Riesgo inmediato para la salud, incumplimiento crítico, contaminación
- MEDIA: Deficiencias operativas, desorden, falta de documentación
- BAJA: Observaciones menores, mejoras de proceso

## INSTRUCCIONES:
1. Identifica cada hallazgo mencionado
2. Mapea a sucursal_id, sucursal_nombre, area y subitem del catálogo
3. Extrae la descripción limpia
4. Asigna severidad (Alta/Media/Baja)
5. Estima confianza (0.0 a 1.0) basada en claridad del mensaje
6. Si faltan datos críticos, lístalos en "datos_faltantes"

## RESPUESTA REQUERIDA (SOLO JSON):
Responde EXCLUSIVAMENTE con un JSON válido, sin markdown ni explicaciones:
{{
  "hallazgos": [
    {{
      "sucursal_id": "...",
      "sucursal_nombre": "...",
      "area": "...",
      "subitem": "...",
      "descripcion": "...",
      "severidad": "Alta|Media|Baja",
      "confianza": 0.0-1.0
    }}
  ],
  "datos_faltantes": ["campo1", "campo2"],
  "mensaje_original_limpio": "..."
}}"""
        except Exception as e:
            logger.error(f"Failed to build system prompt: {e}")
            raise

    async def parse_message(self, message: str) -> Optional[ParserResponse]:
        """Parse audit message and extract findings."""
        try:
            system_prompt = self._build_system_prompt()

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": message,
                    }
                ],
            )

            # Extract and parse JSON response
            response_text = response.content[0].text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Remove ```json
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()
            parsed = json.loads(response_text)

            # Convert to ParserResponse
            hallazgos = []
            for h in parsed.get("hallazgos", []):
                try:
                    hallazgos.append(Hallazgo(
                        sucursal_id=h.get("sucursal_id", ""),
                        sucursal_nombre=h.get("sucursal_nombre", ""),
                        area=h.get("area", ""),
                        subitem=h.get("subitem", ""),
                        descripcion=h.get("descripcion", ""),
                        severidad=Severidad(h.get("severidad", "Baja")),
                        confianza=float(h.get("confianza", 0.5)),
                    ))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse hallazgo: {e}")
                    continue

            result = ParserResponse(
                hallazgos=hallazgos,
                datos_faltantes=parsed.get("datos_faltantes", []),
                mensaje_original_limpio=parsed.get("mensaje_original_limpio", message),
            )

            logger.info(f"Parsed {len(hallazgos)} hallazgos from message")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
            return None

    async def apply_correction(
        self,
        original_message: str,
        correction: str,
        previous_response: ParserResponse,
    ) -> Optional[ParserResponse]:
        """Apply auditor's correction to previous parse."""
        try:
            system_prompt = self._build_system_prompt()
            prompt = f"""El auditor realizó la siguiente corrección:
MENSAJE ORIGINAL: {original_message}
CORRECCIÓN: {correction}
PARSE ANTERIOR: {json.dumps(vars(previous_response), default=str, ensure_ascii=False)}

Por favor, regenera el parse aplicando la corrección."""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response_text = response.content[0].text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()
            parsed = json.loads(response_text)

            hallazgos = []
            for h in parsed.get("hallazgos", []):
                hallazgos.append(Hallazgo(
                    sucursal_id=h.get("sucursal_id", ""),
                    sucursal_nombre=h.get("sucursal_nombre", ""),
                    area=h.get("area", ""),
                    subitem=h.get("subitem", ""),
                    descripcion=h.get("descripcion", ""),
                    severidad=Severidad(h.get("severidad", "Baja")),
                    confianza=float(h.get("confianza", 0.5)),
                ))

            result = ParserResponse(
                hallazgos=hallazgos,
                datos_faltantes=parsed.get("datos_faltantes", []),
                mensaje_original_limpio=parsed.get("mensaje_original_limpio", original_message),
            )

            logger.info(f"Applied correction, resulting in {len(hallazgos)} hallazgos")
            return result
        except Exception as e:
            logger.error(f"Failed to apply correction: {e}")
            return None

    async def evaluate_punto_respuesta(
        self,
        punto: ChecklistPunto,
        respuesta: str,
    ) -> Optional[PuntoEvalResult]:
        """Evaluate auditor's response to a checklist point."""
        try:
            system_prompt = """Sos un auditor de calidad evaluando la respuesta de un inspector de farmacia.
Tu tarea es evaluar si hay un desvío (incumplimiento) en la respuesta.
Respondé EXCLUSIVAMENTE con JSON válido, sin markdown ni explicaciones."""

            prompt = f"""PUNTO AUDITADO:
- Área: {punto.area}
- Qué revisar: {punto.descripcion}
- Severidad por default: {punto.severidad_default}

RESPUESTA DEL AUDITOR:
{respuesta}

Evaluá si hay un desvío. Si la respuesta indica todo OK, tiene_desvio=false y descripcion_desvio vacío.
Si hay un problema, especifica descripcion_desvio y asigna severidad (Alta/Media/Baja).

Responde SOLO con JSON:
{{
  "tiene_desvio": true|false,
  "descripcion_desvio": "descripción del problema o vacío si todo OK",
  "severidad": "Alta|Media|Baja",
  "ok_message": "mensaje corto de confirmación para el auditor"
}}"""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            # Strip markdown if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()
            parsed = json.loads(response_text)

            result = PuntoEvalResult(
                tiene_desvio=bool(parsed.get("tiene_desvio", False)),
                descripcion_desvio=str(parsed.get("descripcion_desvio", "")),
                severidad=str(parsed.get("severidad", punto.severidad_default)),
                ok_message=str(parsed.get("ok_message", "Registrado.")),
            )

            logger.info(f"Evaluated punto {punto.punto_orden}: desvio={result.tiene_desvio}")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse evaluation response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to evaluate punto respuesta: {e}")
            return None

    async def parse_bloque(
        self,
        bloque_id: str,
        bloque_nombre: str,
        items: list[ItemBloque],
        respuesta_auditor: str,
    ) -> Optional[list[ResultadoItem]]:
        """Evaluate auditor's response to a block and assign scores 1-5 to each item."""
        try:
            system_prompt = """Sos un auditor de calidad evaluando la respuesta de un inspector de farmacia.
Tu tarea es evaluar cada ítem del bloque y asignar un puntaje de 1 a 5.

ESCALA DE PUNTAJE:
- 5: Cumplimiento total, estado excelente
- 4: Cumplimiento adecuado con observaciones menores
- 3: Cumplimiento parcial, requiere mejoras
- 2: Incumplimiento significativo
- 1: Incumplimiento total, crítico

Responde EXCLUSIVAMENTE con JSON válido (un array de objetos), sin markdown ni explicaciones."""

            items_text = "\n".join([f"- {item.item_id}: {item.descripcion}" for item in items])

            prompt = f"""BLOQUE {bloque_id} — {bloque_nombre}

ÍTEMS DEL BLOQUE:
{items_text}

RESPUESTA DEL AUDITOR:
{respuesta_auditor}

La respuesta puede ser:
- Números separados por coma (ej: "3,4,4,5,3,2") → mapear en orden a los ítems
- Descripción libre (texto o transcripción de audio) → inferir puntaje y desvíos para cada ítem
- Combinación de números y texto

Evalúa cada ítem en orden y detecta automáticamente desvíos.

Responde SOLO con JSON array, un objeto por ítem en el mismo orden:
[
  {{
    "item_id": "A1",
    "puntaje": 1-5,
    "tiene_desvio": true|false,
    "descripcion_desvio": "descripción del problema o null si no hay desvío",
    "severidad": "Alta"|"Media"|"Baja"|null
  }},
  ...
]"""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            # Strip markdown if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()
            parsed = json.loads(response_text)

            resultados = []
            for item_data in parsed:
                resultado = ResultadoItem(
                    item_id=item_data.get("item_id", ""),
                    puntaje=item_data.get("puntaje"),
                    tiene_desvio=bool(item_data.get("tiene_desvio", False)),
                    descripcion_desvio=item_data.get("descripcion_desvio"),
                    severidad=item_data.get("severidad"),
                )
                resultados.append(resultado)

            logger.info(f"Parsed bloque {bloque_id}: {len(resultados)} items evaluated")
            return resultados
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bloque response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse bloque: {e}")
            return None

    async def parse_stock_item(self, texto: str) -> Optional[StockItem]:
        """Extract stock item (nombre, stock_fisico, stock_sistema) from free text."""
        try:
            system_prompt = """Sos un asistente que extrae información de stock de medicinas.
El auditor proporciona información sobre un producto: nombre y dos números (stock físico / stock sistema).

Ejemplos:
- "Ibuprofeno 400 / 23 / 18" → nombre: "Ibuprofeno 400", fisico: 23, sistema: 18
- "Aspirina 500mg: tengo 10, el sistema dice 15" → nombre: "Aspirina 500mg", fisico: 10, sistema: 15

Responde EXCLUSIVAMENTE con JSON válido, sin markdown ni explicaciones."""

            prompt = f"""Extrae información de stock del siguiente texto:
{texto}

Si puedes extraer la información completa, responde con:
{{
  "nombre": "nombre del producto",
  "stock_fisico": número,
  "stock_sistema": número
}}

Si NO puedes extraer información válida (faltan datos o son incoherentes), responde con:
{{"nombre": null, "stock_fisico": null, "stock_sistema": null}}"""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()
            parsed = json.loads(response_text)

            nombre = parsed.get("nombre")
            fisico = parsed.get("stock_fisico")
            sistema = parsed.get("stock_sistema")

            if nombre and fisico is not None and sistema is not None:
                item = StockItem(
                    nombre=str(nombre),
                    stock_fisico=int(fisico),
                    stock_sistema=int(sistema),
                )
                logger.info(f"Parsed stock item: {item.nombre}")
                return item

            logger.warning(f"Could not extract valid stock item from: {texto}")
            return None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse stock item: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse stock item: {e}")
            return None

    async def parse_desvio_libre(self, texto: str) -> Optional[DesvioLibre]:
        """Extract free-form deviation (area, description, severity) from text."""
        try:
            system_prompt = """Sos un auditor de farmacia analizando observaciones libres.
El auditor reporta un problema o desvío sin seguir una estructura fija.

Tu tarea es extraer:
- área_estimada: área de la farmacia (ej: "Vidriera", "Dispensario", "Caja", etc.)
- descripcion: descripción clara del problema
- severidad: Alta|Media|Baja

Responde EXCLUSIVAMENTE con JSON válido, sin markdown ni explicaciones."""

            prompt = f"""Analiza esta observación de auditoría y extrae los datos:
{texto}

Responde con JSON:
{{
  "area_estimada": "área de la farmacia",
  "descripcion": "descripción del problema",
  "severidad": "Alta"|"Media"|"Baja"
}}

Si no puedes extraer información válida, responde con:
{{"area_estimada": null, "descripcion": null, "severidad": null}}"""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()
            parsed = json.loads(response_text)

            area = parsed.get("area_estimada") or "Observación libre"
            desc = parsed.get("descripcion")
            sev = parsed.get("severidad") or "Media"

            if desc:
                desvio = DesvioLibre(
                    area_estimada=str(area),
                    descripcion=str(desc),
                    severidad=str(sev),
                )
                logger.info(f"Parsed desvio libre: {area}")
                return desvio

            logger.warning(f"Could not extract valid desvio from: {texto}")
            return None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse desvio libre: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse desvio libre: {e}")
            return None
