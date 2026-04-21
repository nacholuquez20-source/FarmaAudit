# CODEX_TASKS.md — Tareas de Generación de Código

Este archivo lista tareas de código boilerplate o repetitivo que pueden ser delegadas a Codex u otro asistente de generación de código.

---

## TAREA CODEX N°1: Métodos CRUD adicionales en SheetsManager

**Archivo**: `sheets.py`

**Función**: `get_reportes_by_date(fecha: str) -> List[Reporte]`

**Prompt**: "Escribí una función Python async llamada `get_reportes_by_date` que:
- Recibe una fecha en formato 'YYYY-MM-DD'
- Lee la hoja 'Reportes' con gspread
- Filtra filas donde la columna 'Fecha' coincida exactamente
- Convierte cada fila en un objeto `Reporte` (importado de models.py)
- Retorna una lista de Reportes
- Manejá excepciones con logging
- Usa logger.info para registrar cuántos reportes se encontraron"

**Ejemplo de input**: `get_reportes_by_date("2026-04-20")`

**Ejemplo de output esperado**: `[Reporte(...), Reporte(...), ...]`

---

## TAREA CODEX N°2: Métodos de consulta en SheetsManager

**Archivo**: `sheets.py`

**Función**: `get_gestiones_by_estado(estado: GestionState) -> List[Gestion]`

**Prompt**: "Escribí una función Python async llamada `get_gestiones_by_estado` que:
- Recibe un enum `GestionState` (importado de models.py)
- Lee la hoja 'Gestion' con gspread
- Filtra filas donde la columna 'Estado' == estado.value
- Convierte cada fila en un objeto `Gestion`
- Retorna una lista de Gestiones
- Manejá excepciones con logging"

---

## TAREA CODEX N°3: Métodos de estadísticas diarias

**Archivo**: `sheets.py`

**Función**: `get_daily_stats(fecha: str) -> dict`

**Prompt**: "Escribí una función Python que:
- Recibe una fecha en formato 'YYYY-MM-DD'
- Lee reportes del día con `get_reportes_by_date(fecha)`
- Calcula:
  - Total de reportes
  - Conteo por severidad (Alta/Media/Baja)
  - Sucursales afectadas (lista sin duplicar)
  - Conteo por área
- Retorna un diccionario con estructura:
```python
{
    'total': int,
    'por_severidad': {'Alta': int, 'Media': int, 'Baja': int},
    'sucursales': List[str],
    'por_area': {area: count, ...}
}
```"

---

## TAREA CODEX N°4: Métodos de validación en SheetsManager

**Archivo**: `sheets.py`

**Función**: `validate_hallazgo(hallazgo: Hallazgo) -> Tuple[bool, str]`

**Prompt**: "Escribí una función Python que:
- Recibe un objeto `Hallazgo` (importado de models.py)
- Valida que:
  - sucursal_id exista en Maestro_Sucursales (usa `get_sucursal`)
  - area esté en el catálogo (usa `get_all_areas`)
  - subitem esté dentro de los subitems del area
  - descripcion no esté vacía
  - severidad sea uno de: Alta, Media, Baja
  - confianza esté entre 0.0 y 1.0
- Retorna tupla (bool, str):
  - True, 'OK' si todo es válido
  - False, 'Error message' si hay problema
- Usa logger para registrar validaciones fallidas"

---

## TAREA CODEX N°5: Formatter de resumen diario completo

**Archivo**: `main.py` (reemplazar función `daily_summary_job`)

**Prompt**: "Escribí una función Python async llamada `daily_summary_job` que:
- Obtiene la fecha actual con `datetime.now().strftime('%Y-%m-%d')`
- Llama a `sheets.get_daily_stats(fecha)` para obtener estadísticas
- Obtiene reportes vencidos de 'Gestion' donde fecha_cierre es None y plazo_fecha < ahora
- Genera un mensaje WhatsApp formateado así:
```
📊 **Resumen Diario AuditBot**
Fecha: 2026-04-20

📈 **Hallazgos del día**: {total}
  🔴 Severidad Alta: {count}
  🟡 Severidad Media: {count}
  🟢 Severidad Baja: {count}

🏥 **Sucursales afectadas**: {lista}

📋 **Por Área**:
  {area}: {count}
  ...

⏰ **Gestiones vencidas**: {count}

```
- Envía el mensaje al coordinador (settings.coordinador_tel) con WAHA
- Usa try/except con logging"

---

## TAREA CODEX N°6: Query helpers para reportes

**Archivo**: `sheets.py`

**Funciones múltiples**: 
- `get_reportes_by_cuadrilla(cuadrilla: str, fecha: str) -> List[Reporte]`
- `get_reportes_by_sucursal(id_sucursal: str) -> List[Reporte]`
- `get_reportes_by_auditor(nombre_auditor: str, fecha: str) -> List[Reporte]`

**Prompt**: "Escribí tres funciones Python que:
1. `get_reportes_by_cuadrilla(cuadrilla: str, fecha: str)` → filtra por cuadrilla + fecha
2. `get_reportes_by_sucursal(id_sucursal: str)` → filtra por ID sucursal (sin filtro fecha)
3. `get_reportes_by_auditor(nombre_auditor: str, fecha: str)` → filtra por auditor + fecha

Cada una:
- Lee la hoja 'Reportes'
- Filtra según criterios
- Retorna List[Reporte]
- Usa logger.info para contar matches
- Manejá excepciones"

---

## TAREA CODEX N°7: Método de actualización de gestión

**Archivo**: `sheets.py`

**Función**: `update_gestion_estado(id_gestion: str, nuevo_estado: GestionState, fecha_cierre: Optional[datetime] = None, cerrado_por: Optional[str] = None) -> bool`

**Prompt**: "Escribí una función Python que:
- Recibe id_gestion, nuevo_estado (enum GestionState), y opcionalmente fecha_cierre y cerrado_por
- Busca la fila en 'Gestion' donde ID_Gestion == id_gestion
- Actualiza la columna 'Estado' con nuevo_estado.value
- Si fecha_cierre no es None, actualiza la columna 'Fecha_cierre'
- Si cerrado_por no es None, actualiza la columna 'Cerrado_por'
- Retorna True si fue exitoso, False si no encontró la gestión
- Usa logger.info para registrar la actualización"

---

## TAREA CODEX N°8: Integración de /mis y /resumen en router.py

**Archivo**: `router.py`

**Funciones**: Reemplazar funciones stub en `_handle_command`

**Prompt**: "Mejorá las funciones `/resumen` y `/mis` en `_handle_command`:

Para `/resumen`:
- Llama a `sheets.get_daily_stats(datetime.now().strftime('%Y-%m-%d'))`
- Genera un mensaje similar al resumen diario (ver TAREA CODEX N°5)
- Envía vía WAHA al auditor

Para `/mis`:
- Obtiene el nombre del auditor desde el objeto auditor pasado
- Llama a `sheets.get_reportes_by_auditor(auditor.nombre, fecha_hoy)`
- Genera mensaje:
```
📄 **Mis Reportes - {fecha}**

Total: {count}
{lista de reportes con sucursal, área, severidad}
```
- Envía vía WAHA"

---

## TAREA CODEX N°9: Paginación de reportes en SheetsManager

**Archivo**: `sheets.py`

**Función**: `get_reportes_paginated(page: int = 1, page_size: int = 10) -> Tuple[List[Reporte], int]`

**Prompt**: "Escribí una función Python que:
- Recibe page (número de página, 1-indexed) y page_size
- Lee TODA la hoja 'Reportes'
- Calcula offset: (page - 1) * page_size
- Retorna tupla:
  - Lista de Reportes para esa página
  - Total de páginas (ceil(total_rows / page_size))
- Ejemplo: `get_reportes_paginated(2, 10)` retorna reportes 11-20 de la hoja"

---

## TAREA CODEX N°10: Exportar reportes a CSV

**Archivo**: `sheets.py`

**Función**: `export_reportes_csv(fecha: str) -> str`

**Prompt**: "Escribí una función Python que:
- Obtiene reportes del día con `get_reportes_by_date(fecha)`
- Convierte a CSV con headers: ID,Fecha,Hora,Cuadrilla,Auditor,Sucursal,Area,SubItem,Descripcion,Severidad,Foto,CreadoPorAudio
- Retorna el contenido CSV como string
- Nota: importá csv module"

---

## INSTRUCCIONES DE USO

Cuando uses Codex para generar código:
1. Copiá el **Prompt** exacto de la tarea
2. Paste en Codex con el contexto del archivo
3. Validá que el código siga el estilo del proyecto:
   - Type hints en todas las funciones
   - Docstrings con """..."""
   - Logging en puntos clave
   - Manejo de excepciones
4. Integrá el código en el archivo especificado
5. Probá la función si es posible
