# AuditBot — Quick Start

## Estado Actual

✅ **Proyecto completamente construido**
✅ **FastAPI app inicializa correctamente**
✅ **Módulos cargados sin errores**
✅ **Credenciales parcialmente configuradas**

## Próximos Pasos

### 1. Configurar Google Service Account

```bash
# Obtené el JSON de Google Cloud Console:
# https://console.cloud.google.com/iam-admin/serviceaccounts

# Copiá el JSON descargado a esta carpeta:
cp ~/Downloads/proyecto-trello-487919-xxx.json ./service-account.json

# Ejecutá el setup script:
python setup_env.py
```

El script va a:
- Leer el service-account.json
- Codificarlo a base64
- Actualizar el .env automáticamente

### 2. Crear Google Sheets

Seguí [SETUP_SHEETS.md](SETUP_SHEETS.md) para crear:
- ✅ Maestro_Auditores
- ✅ Maestro_Sucursales
- ✅ Catalogo_Areas
- ✅ Conversaciones
- ✅ Pendientes
- ✅ Reportes
- ✅ Gestion

**ID del Sheets ya configurado**: `1xr8SWxVNzGJbQNXn1WDJjOw2wjlq0TJl-l1024jn60Q`

### 3. Instalar Dependencias Completas

```bash
pip install -r requirements.txt
```

### 4. Probar Localmente

```bash
# Desarrollo (con reload):
python main.py

# O con uvicorn:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Testear en:
- Health check: http://localhost:8000/health
- Docs: http://localhost:8000/docs

### 5. Probar Webhook

Con curl o Postman:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "5491166666666@c.us",
    "type": "text",
    "text": "Puntera de perfumería desordenada",
    "caption": null,
    "media": null
  }'
```

### 6. Configurar WAHA Webhook

En tu instancia WAHA:
- Endpoint: `https://tu-app.railway.app/webhook` (cuando deployés)
- Método: POST
- Eventos: message.received

### 7. Deploy en Railway

```bash
# 1. Inicializar git
git init
git add .
git commit -m "Initial commit"

# 2. Crear repo en GitHub
# https://github.com/new

# 3. Push
git remote add origin https://github.com/tu-usuario/auditbot.git
git branch -M main
git push -u origin main

# 4. En Railway
# - New Project
# - Connect GitHub
# - Seleccionar repo
# - Agregar variables de entorno (.env)
# - Deploy automático
```

## Estructura de Carpetas

```
auditbot/
├── main.py              # FastAPI app ✅
├── router.py            # State machine ✅
├── parser.py            # Claude parser ✅
├── sheets.py            # Google Sheets CRUD ✅
├── waha.py              # WhatsApp client ✅
├── audio.py             # Whisper transcription ✅
├── drive.py             # Google Drive upload ✅
├── models.py            # Data models ✅
├── config.py            # Config + .env ✅
├── setup_env.py         # Setup helper ✅
├── requirements.txt     # Dependencies ✅
├── Dockerfile           # Docker config ✅
├── .env                 # Environment (actual) ⚠️ NUNCA COMMITEES
├── .env.example         # Template ✅
├── .gitignore           # Git ignores ✅
├── README.md            # Full documentation ✅
├── QUICK_START.md       # This file
├── SETUP_SHEETS.md      # Sheets setup guide ✅
├── CODEX_TASKS.md       # Code generation tasks ✅
└── service-account.json # Google credentials (local, ignored)
```

## Variables de Entorno Requeridas

| Variable | Estado | Obtener de |
|----------|--------|-----------|
| `ANTHROPIC_API_KEY` | ✅ Configurado | console.anthropic.com |
| `OPENAI_API_KEY` | ✅ Configurado | platform.openai.com |
| `WAHA_URL` | ✅ Configurado | https://waha-production-0227.up.railway.app |
| `WAHA_API_KEY` | ✅ Configurado | auditbot123 |
| `GOOGLE_SHEETS_ID` | ✅ Configurado | 1xr8SWx... |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ⚠️ Pendiente | setup_env.py |
| `GOOGLE_DRIVE_FOLDER_ID` | ✅ Configurado | 1Rs5pfc... |

## Troubleshooting

### Error: "Missing GOOGLE_SERVICE_ACCOUNT_JSON"
→ Ejecutá `python setup_env.py` después de obtener el JSON

### Error: "service-account.json no encontrado"
→ Descargá desde https://console.cloud.google.com/iam-admin/serviceaccounts

### Error en webhook: "Auditor no encontrado"
→ Agregá un auditor en la hoja Maestro_Auditores

### Error al parsear hallazgo
→ Verificá que el catálogo de áreas tenga SubItems válidos en JSON

## Testing

```bash
# Verificar que FastAPI inicia
python -c "from main import app; print('OK')"

# Verificar módulos
python -c "import config, models, sheets, waha, parser; print('OK')"

# Verificar Google Sheets (después de setup_env.py)
python -c "from sheets import SheetsManager; m = SheetsManager(); print('OK')"
```

## Próximas Features

- [ ] Daily summary fully implemented
- [ ] /resumen command complete
- [ ] /mis command complete
- [ ] Tests automatizados
- [ ] Dashboard de reportes
- [ ] Exportación CSV/PDF

## Support

Ver README.md para más detalles sobre:
- Flujo de conversación completo
- API endpoints
- Background jobs
- Configuración de severidad
- FAQ

---

**Estado**: Listo para testing local
**Próximo paso**: Ejecutá `python setup_env.py`
