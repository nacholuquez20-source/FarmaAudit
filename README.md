# AuditBot — Sistema QA para Farmacias

Sistema de auditoría de calidad para 23 sucursales de farmacias vía WhatsApp. Los auditores envían hallazgos (texto, audio, fotos), el sistema parsea con IA, solicita confirmación, y genera reportes + planes de acción automáticos.

## Features

✅ **WhatsApp Integration** — WAHA API para mensajería bidireccional
✅ **IA Parser** — Claude Sonnet para extracción de hallazgos
✅ **Audio Transcription** — OpenAI Whisper para mensajes de voz
✅ **Photo Storage** — Google Drive para fotos de auditoría
✅ **State Machine** — Flujo de confirmación y edición
✅ **Auto-Management** — Creación automática de planes de acción
✅ **Background Jobs** — Timeouts de confirmación y resúmenes diarios
✅ **MVP Database** — Google Sheets como base de datos

## Tech Stack

- **Framework**: FastAPI + uvicorn
- **IA**: Anthropic Claude Sonnet API
- **Audio**: OpenAI Whisper API
- **Database**: Google Sheets (gspread)
- **Storage**: Google Drive API
- **Messaging**: WAHA (WhatsApp HTTP API)
- **Scheduling**: APScheduler
- **Deployment**: Railway (Docker)

## Prerequisites

- Python 3.11+
- Google Cloud Project con habilitadas:
  - Google Sheets API
  - Google Drive API
- Service Account credentials (JSON)
- WAHA instance en Railway
- Anthropic API key
- OpenAI API key

## Installation

### 1. Cloná el repo y creá virtualenv

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Instalá dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurá Google Sheets

Seguí las instrucciones en [SETUP_SHEETS.md](SETUP_SHEETS.md) para crear las hojas y obtener credenciales.

### 4. Copía y completá .env

```bash
cp .env.example .env
```

Completá todos los valores en `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
WAHA_URL=https://waha-production-0227.up.railway.app
WAHA_API_KEY=auditbot123
WAHA_SESSION=default
GOOGLE_SHEETS_ID=xxxxxxxxxxxxxxxxxxxxx
GOOGLE_SERVICE_ACCOUNT_JSON=xxxxxxxxxxxxxxxxxxxxx  # Base64-encoded
GOOGLE_DRIVE_FOLDER_ID=xxxxxxxxxxxxxxxxxxxxx
COORDINADOR_TEL=549xxxxxxxxxx
```

**Para obtener GOOGLE_SERVICE_ACCOUNT_JSON en base64:**

```bash
# Windows (PowerShell)
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("path\to\service-account.json"))

# Linux/Mac
cat service-account.json | base64
```

## Running Locally

```bash
python main.py
```

O con uvicorn directamente:

```bash
uvicorn main:app --reload --port 8000
```

La aplicación estará en `http://localhost:8000`

### Health Check

```bash
curl http://localhost:8000/health
```

## Deployment en Railway

### 1. Creá repo en GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/username/auditbot.git
git push -u origin main
```

### 2. Deployá en Railway

1. Abrí [railway.app](https://railway.app)
2. New Project → GitHub Repo
3. Seleccioná tu repo
4. Railway auto-detecta Dockerfile
5. Agregá variables de entorno en Project Settings:
   - ANTHROPIC_API_KEY
   - OPENAI_API_KEY
   - WAHA_URL, WAHA_API_KEY, WAHA_SESSION
   - GOOGLE_SHEETS_ID
   - GOOGLE_SERVICE_ACCOUNT_JSON
   - GOOGLE_DRIVE_FOLDER_ID
   - COORDINADOR_TEL

### 3. Configurá WAHA webhook

En WAHA panel, configurá el webhook a:

```
https://tu-railway-app.up.railway.app/webhook
```

Con método POST.

## API Endpoints

### `GET /health`

Health check endpoint.

```bash
curl http://localhost:8000/health
```

### `POST /webhook`

WAHA webhook entry point. Recibe mensajes de WhatsApp.

**Payload:**
```json
{
  "phone": "549XXXXXXXXXX@c.us",
  "type": "text|audio|image",
  "text": "opcional: texto del mensaje",
  "media": {"url": "https://..."}
}
```

## Flujo de Conversación

```
AUDITOR                             AUDITBOT
   │
   ├─> envía hallazgo (texto)      ──> valida auditor
   │                                  ├─> parsea con Claude
   │                                  ├─> crea pendiente
   │                                  └─> muestra borrador
   │
   ├─> "SI" / "NO" / "EDITAR"      ──> procesa confirmación
   │                                  ├─> si SI: crea reportes
   │                                  ├─> notifica responsables
   │                                  └─> resetea conversación
   │
   └─> timeout (5 min)             ──> background job
                                       ├─> cancela pendiente
                                       ├─> resetea estado
                                       └─> notifica auditor
```

## Comandos Especiales

- `/ayuda` — Muestra instrucciones de uso
- `/resumen` — Resumen del día actual
- `/mis` — Mis reportes de hoy

## Configuración de Severidad

| Severidad | Plazo   | Descripción                                          |
|-----------|---------|------------------------------------------------------|
| Alta      | 24h     | Riesgo inmediato para salud, incumplimiento crítico  |
| Media     | 72h     | Deficiencias operativas, desorden, falta docs       |
| Baja      | 7 días  | Observaciones menores, mejoras de proceso           |

## Background Jobs

### Timeout Check (cada 2 minutos)

- Revisa tabla `Pendientes`
- Identifica confirmaciones expiradas
- Notifica al auditor
- Resetea conversación

### Daily Summary (20:00 ART = 23:00 UTC)

- Genera resumen del día
- Cuenta hallazgos por severidad
- Enlista sucursales afectadas
- Reporta gestiones vencidas
- Envía al coordinador

## Estructura de Archivos

```
auditbot/
├── main.py              # FastAPI app + webhooks + background jobs
├── router.py            # State machine logic
├── parser.py            # Claude API integration
├── sheets.py            # Google Sheets CRUD
├── waha.py              # WAHA client
├── audio.py             # Whisper transcription
├── drive.py             # Google Drive upload
├── models.py            # Pydantic/dataclass models
├── config.py            # Environment variables
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container config
├── .env.example         # Example environment
├── README.md            # This file
├── SETUP_SHEETS.md      # Google Sheets setup guide
└── CODEX_TASKS.md       # Code generation tasks
```

## Development

### Logging

La aplicación usa módulo `logging` estándar. Para ver logs en desarrollo:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Mensaje informativo")
logger.error("Mensaje de error")
```

### Cache

`Maestro_Sucursales` y `Catalogo_Areas` se cachean por 5 minutos para mejorar performance:

```python
sheets = SheetsManager()
sucursales = sheets.get_all_sucursales()  # Cached
```

### Testing

(Por implementar)

## Troubleshooting

### "Missing required environment variables"

Asegurate que el archivo `.env` existe y tiene todas las variables.

### "Failed to initialize Google Sheets"

- Verificá que el GOOGLE_SERVICE_ACCOUNT_JSON sea válido base64
- Compartí el spreadsheet con el email del Service Account
- Creá todas las hojas descritas en SETUP_SHEETS.md

### WAHA no recibe/envía mensajes

- Verificá que WAHA_URL, WAHA_API_KEY y WAHA_SESSION sean correctos
- Confirmá que el webhook en WAHA apunta a `{app_url}/webhook`
- Revísá los logs de WAHA para errores

### Claude parser devuelve JSON inválido

- Incrementá `max_tokens` en parser.py si los hallazgos son muy largos
- Validá que el catálogo de areas tenga JSON válido en SubItems

## FAQ

**¿Puedo usar otra BD en lugar de Google Sheets?**

Sí, modificá `sheets.py` para usar tu DB preferida. La interfaz es la misma.

**¿Cuál es el límite de auditores/sucursales?**

Google Sheets puede manejar ~100k filas. Para 23 sucursales + miles de reportes, no hay problema.

**¿Los audios se guardan?**

Los audios se transcriben con Whisper y se descartan. Las fotos se guardan en Google Drive.

**¿Qué sucede si un hallazgo tiene errores en el parser?**

El auditor puede editar el hallazgo con "EDITAR" y Claude re-procesa con la corrección.

## License

MIT

## Support

Para issues, features requests, o preguntas:
- Creá un issue en GitHub
- Contactá al equipo de desarrollo

---

**AuditBot v1.0** — 2026-04-20
