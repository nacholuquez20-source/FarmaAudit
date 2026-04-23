# Resumen: Configuración de Meta WhatsApp Cloud API

## Estado Actual
- **Proyecto**: FarmaAudit (WhatsApp QA audit system)
- **Integración**: Meta WhatsApp Cloud API
- **Deployment**: Railway en `farmaaudit-production-3f78.up.railway.app`
- **Código**: Webhook JSON de Meta integrado

## Archivos Modificados
- `config.py`: variables `META_*`
- `meta_client.py`: cliente de Meta WhatsApp Cloud API
- `main.py`: webhook JSON para mensajes entrantes de Meta
- `router.py`: integra el flujo de conversaciones
- `requirements.txt`: dependencias de FastAPI, gspread, Anthropic, OpenAI
- `.env.example`: variables actualizadas

## Problema Actual
La cuenta de Meta/WhatsApp debe tener:
- App de Meta configurada
- Número de teléfono habilitado en WhatsApp Cloud API
- Webhook verificado con `META_VERIFY_TOKEN`

## Dos Opciones para Resolver

### Opción A: Testing Inmediato
1. Cambiar `.env`:
   ```
   META_PHONE_NUMBER_ID=123456789012345
   META_ACCESS_TOKEN=your_meta_access_token_here
   META_VERIFY_TOKEN=your_verify_token_here
   ```
2. Push a Git → Railway redeploy
3. Enviar un WhatsApp al número habilitado en Meta
4. Webhook debería recibir mensaje en Railway logs

### Opción B: Producción
1. Completar la verificación de la app en Meta Business
2. Confirmar el número de WhatsApp Business habilitado
3. Revisar que el webhook de producción apunte a Railway
4. Validar el envío y recepción de mensajes

## Qué Necesita Codex
Si continuás con setup:
1. Decidir Opción A o B
2. Si Opción A: completar variables `META_*` y push
3. Si Opción B: completar verificación en Meta Console
4. Prueba end-to-end: mandar WhatsApp → verificar logs Railway → respuesta del bot

## Variables del .env en Production
```
# Meta WhatsApp Cloud API
META_PHONE_NUMBER_ID=123456789012345
META_ACCESS_TOKEN=your_meta_access_token_here
META_VERIFY_TOKEN=your_verify_token_here
```

## Webhook
- **URL en Meta Developers**: `https://farmaaudit-production-3f78.up.railway.app/webhook`
- **Method**: POST
- **Content-Type**: application/json
- **Endpoint en código**: `/webhook` en `main.py`, maneja WAHAPayload, parsea JSON
