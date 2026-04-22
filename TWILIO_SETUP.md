# Resumen: Migración de Evolution API a Twilio WhatsApp Business API

## Estado Actual
- **Proyecto**: FarmaAudit (WhatsApp QA audit system)
- **Migración**: Completada de Evolution API → Twilio SDK
- **Deployment**: Railway en `farmaaudit-production-3f78.up.railway.app`
- **Código**: Twilio SDK integrado, webhook form-data parsing funcionando

## Archivos Modificados
- `config.py`: WAHA vars → TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
- `waha.py`: WAHAClient reescrito → TwilioClient (twilio.rest.Client + asyncio.run_in_executor)
- `main.py`: Webhook reescrito para form-data (Twilio format, no JSON)
- `router.py`: WAHAClient → TwilioClient refs
- `requirements.txt`: +twilio==8.10.0
- `.env.example`: Variables actualizadas

## Problema Actual
Cuenta Twilio está en **TRIAL/SANDBOX MODE**:
- No puede enviar mensajes a números no verificados
- Webhook está correctamente configurado en URL Railway
- Pero número +12603668019 no está en producción

## Dos Opciones para Resolver

### Opción A: Testing Inmediato (Sandbox)
1. Cambiar `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token_here
   TWILIO_PHONE_NUMBER=+14155238886  # Sandbox number, no +12603668019
   ```
2. Push a Git → Railway redeploy
3. Enviar WhatsApp al +14155238886 con código: `join gray-whose`
4. Webhook debería recibir mensaje en Railway logs

### Opción B: Producción (WhatsApp Business API)
1. Upgrade cuenta Twilio (salir de trial)
2. Seguir verificación WhatsApp Business oficial
3. Usar número +12603668019 en producción
4. Toma 1-2 días de verificación

## Qué Necesita Codex
Si continúas con setup:
1. Decidir Opción A o B
2. Si Opción A: actualizar TWILIO_PHONE_NUMBER a +14155238886 y push
3. Si Opción B: completar verificación en Twilio Console
4. Prueba end-to-end: mandar WhatsApp → verificar logs Railway → respuesta del bot

## Variables del .env en Production
```
# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+12603668019  # (o +14155238886 si Sandbox)
```

## Webhook
- **URL en Twilio Console**: `https://farmaaudit-production-3f78.up.railway.app/webhook`
- **Method**: POST
- **Content-Type**: form-data (Twilio default)
- **Endpoint en código**: `/webhook` en `main.py`, maneja WAHAPayload, parsea form-data
