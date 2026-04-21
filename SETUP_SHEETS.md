# Setup — Google Sheets para AuditBot

Antes de deployar, creá estas hojas en tu Google Sheets. El spreadsheet debe estar compartido con tu Service Account de Google.

## Hoja: Maestro_Auditores

Columnas:
- **Telefono** (String): Número sin símbolos (ej: 5491166666666)
- **Nombre** (String): Nombre del auditor
- **Cuadrilla** (String): Equipo al que pertenece
- **Activo** (Boolean): "true" o "false"

Ejemplo:
```
Telefono             | Nombre          | Cuadrilla | Activo
5491166666666        | Juan Pérez      | Centro    | true
5491177777777        | María García    | Norte     | true
```

---

## Hoja: Maestro_Sucursales

Columnas:
- **ID** (String): Código único (ej: "001")
- **Nombre** (String): Nombre de la sucursal
- **Dirección** (String): Dirección física
- **Responsable** (String): Responsable de la sucursal
- **Tel_Responsable** (String): Teléfono del responsable
- **Zona** (String): Zona geográfica

Ejemplo:
```
ID   | Nombre              | Dirección              | Responsable    | Tel_Responsable | Zona
001  | Farmacia Centro     | Av. Main 100, CABA     | Carlos López   | 5491188888888  | Centro
002  | Farmacia Norte      | Sarmiento 500, CABA    | Ana Martínez   | 5491199999999  | Norte
```

---

## Hoja: Catalogo_Areas

Columnas:
- **Area** (String): Nombre del área/departamento
- **SubItems** (JSON Array): Sub-items dentro del área

Ejemplo:
```
Area           | SubItems
Perfumería     | ["puntera", "stand end", "heladera", "exhibidor"]
Farmacia       | ["estante principal", "refrigerador", "mostrador"]
Caja           | ["caja registradora", "dinero en caja", "cartel de precios"]
Limpieza       | ["piso", "vitrinas", "baños", "entrada"]
```

**Nota**: El JSON debe ser válido. Los subitems se cargan automáticamente en el prompt del parser.

---

## Hoja: Conversaciones

Columnas:
- **Telefono** (String): Teléfono del auditor
- **Estado_actual** (String): "idle", "esperando_confirmacion" o "esperando_edicion"
- **ID_pendiente** (String): ID del pendiente activo (vacío si idle)
- **Ultimo_mensaje** (String): Último mensaje recibido (para referencia)
- **Timestamp** (DateTime): Última actualización

Ejemplo:
```
Telefono      | Estado_actual            | ID_pendiente | Ultimo_mensaje              | Timestamp
5491166666666 | idle                     |              | Listo para nuevo hallazgo   | 2026-04-20T15:30:00
5491177777777 | esperando_confirmacion   | abc12345     | Puntera desordenada         | 2026-04-20T15:25:00
```

---

## Hoja: Pendientes

Columnas:
- **ID_temp** (String): Identificador temporal único
- **Telefono_Auditor** (String): Teléfono del auditor
- **Estado** (String): "esperando_confirmacion" o "esperando_edicion"
- **Datos_JSON** (Text): JSON con el parse y datos del reporte
- **Timestamp_creacion** (DateTime): Cuándo se creó
- **Expira_en** (DateTime): Cuándo expira la confirmación

Ejemplo:
```
ID_temp  | Telefono_Auditor | Estado                | Datos_JSON            | Timestamp_creacion     | Expira_en
abc12345 | 5491166666666    | esperando_confirmacion| {"auditor": "Juan"... | 2026-04-20T15:25:00   | 2026-04-20T15:30:00
```

---

## Hoja: Reportes

Columnas:
- **ID** (String): ID único generado automáticamente
- **Fecha** (Date): YYYY-MM-DD
- **Hora** (Time): HH:MM:SS
- **Cuadrilla** (String): Equipo del auditor
- **Auditor** (String): Nombre del auditor
- **ID_Sucursal** (String): ID de la sucursal (foreign key)
- **Sucursal** (String): Nombre de la sucursal
- **Area** (String): Área auditada
- **SubItem** (String): Sub-item del área
- **Descripcion** (String): Descripción del hallazgo
- **Severidad** (String): "Alta", "Media" o "Baja"
- **FotoURL** (String): URL de la foto en Google Drive (si existe)
- **Creado_por_audio** (Boolean): "true" si se creó desde audio
- **Timestamp** (DateTime): Cuándo se creó el reporte

Ejemplo:
```
ID      | Fecha      | Hora     | Cuadrilla | Auditor    | ID_Sucursal | Sucursal        | Area        | SubItem         | Descripcion              | Severidad | FotoURL | Creado_por_audio
rep001  | 2026-04-20 | 15:30:00 | Centro    | Juan Pérez | 001         | Farmacia Centro | Perfumería  | puntera         | Puntera desordenada      | Media     | https://... | false
```

---

## Hoja: Gestion

Columnas:
- **ID_Gestion** (String): ID único generado automáticamente
- **ID_Reporte** (String): ID del reporte asociado (foreign key)
- **ID_Sucursal** (String): ID de la sucursal (foreign key)
- **Sucursal** (String): Nombre de la sucursal
- **Desvio** (String): Descripción del desvío/hallazgo
- **Severidad** (String): "Alta", "Media" o "Baja"
- **Responsable** (String): Responsable de cerrar la gestión
- **Tel_Responsable** (String): Teléfono del responsable
- **Plazo_fecha** (DateTime): Plazo para resolver (calculado automáticamente)
- **Plan_accion** (String): Plan de acción (inicialmente "[Por definir por el responsable]")
- **Estado** (String): "Abierta", "En_proceso" o "Cerrada"
- **Fecha_cierre** (DateTime): Cuándo se cerró (vacío si abierta)
- **Cerrado_por** (String): Quién cerró la gestión (vacío si abierta)

Ejemplo:
```
ID_Gestion | ID_Reporte | ID_Sucursal | Sucursal        | Desvio                   | Severidad | Responsable    | Tel_Responsable | Plazo_fecha         | Plan_accion                       | Estado   | Fecha_cierre | Cerrado_por
gest001    | rep001     | 001         | Farmacia Centro | Puntera desordenada      | Media     | Carlos López   | 5491188888888   | 2026-04-23T15:30:00 | [Por definir por el responsable]  | Abierta  |              |
```

---

## Pasos para Setup

1. Creá un Google Sheets nuevo (o usá uno existente)
2. Creá cada hoja con sus columnas respectivas
3. Agregá al menos un auditor y una sucursal de ejemplo
4. Completá el catálogo de áreas con subitems JSON válido
5. Obtené el ID del spreadsheet (está en la URL: `/spreadsheets/d/{ID}`)
6. Creá un Service Account en Google Cloud Console
7. Descargá el JSON de credenciales
8. Encodá el JSON en base64: `cat service-account.json | base64`
9. Copiá la salida en la variable de entorno `GOOGLE_SERVICE_ACCOUNT_JSON`
10. Compartí el spreadsheet con el email del Service Account
11. Completá el archivo `.env` con todas las variables

---

## Inicializando Las Tablas

```python
# Script para crear tablas vacías con headers correctos
# Ejecutá esto una sola vez al inicio

from sheets import SheetsManager

manager = SheetsManager()

# Las hojas deben estar creadas manualmente en Google Sheets
# Este script solo verifica que existan y que tengan los headers correctos
```

---

## Tips

- **Timestamps**: Usá formato ISO 8601 (YYYY-MM-DDTHH:MM:SS)
- **JSON en SubItems**: Asegurate que sea válido JSON array con strings
- **Teléfonos**: Sin símbolos ni espacios (ej: 5491166666666, no +54 911 666 6666)
- **Backup**: Hacé backup del Google Sheets regularmente
- **Permisos**: El Service Account debe tener permiso de editor en el spreadsheet
