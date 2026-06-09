# Fase 1 Implementation Guide - Estructura Base

**Status**: ✅ Componentes creados  
**Files Created**: 
- `audit_session.py` ✅
- `audit_handlers.py` ✅

**Next**: Integración en router.py

---

## 📝 Paso 1: Agregar imports a router.py

**Agregar después de línea 41 en router.py**:

```python
# NEW: Imports for perfumery audit flow (v2)
from audit_session import (
    AuditSession, AuditState, create_session, get_session, save_session,
    BloqueType, BrandType, BLOQUE_ORDER, BRAND_ORDER
)
from audit_handlers import AuditConversationHandler
```

---

## 🔌 Paso 2: Agregar método a ConversationRouter

**Agregar en la clase `ConversationRouter` (después del método `__init__`)**:

```python
async def handle_perfumeria_audit(
    self,
    payload: WhatsAppPayload,
    meta_client: MetaClient,
) -> str:
    """Handle perfumery audit v2 (structured flow)."""
    
    # Acquire lock for this phone
    lock = await self._get_conversation_lock(payload.telefono)
    
    async with lock:
        try:
            result = await AuditConversationHandler.handle_message(
                payload, meta_client
            )
            return result
        except Exception as e:
            logger.error(f"Error in perfumery audit handler: {e}")
            await meta_client.send_text(
                payload.telefono,
                "❌ Error en la auditoría. Por favor intenta de nuevo."
            )
            return "error"
```

---

## 🎯 Paso 3: Modificar handle_message en router.py

**En el método `_handle_message_locked`, agregar ANTES del último `if conv.estado_actual == ConversationState.IDLE`**:

```python
# Check if it's a perfumery audit v2 trigger
if payload.tipo == "text" and payload.contenido:
    trigger = payload.contenido.lower().strip()
    # Keywords to trigger new perfumery audit flow
    if any(word in trigger for word in ["perfumeria v2", "auditar perfume", "auditoria estructurada"]):
        return await self.handle_perfumeria_audit(payload, meta_client)

# Check if user has active perfumery session
session = get_session(payload.telefono)
if session and session.estado != AuditState.DONE:
    return await self.handle_perfumeria_audit(payload, meta_client)
```

---

## 💾 Paso 4: Crear tabla en Supabase (Opcional)

Si deseas persistencia en BD (en lugar de solo memoria):

```sql
-- NEW TABLE: audit_sessions_pending
CREATE TABLE IF NOT EXISTS audit_sessions_pending (
    id_sesion VARCHAR(100) PRIMARY KEY,
    telefono VARCHAR(20) NOT NULL,
    sucursal_id VARCHAR(100) NOT NULL,
    auditor_nombre VARCHAR(100),
    estado VARCHAR(50) NOT NULL,
    bloques JSONB DEFAULT '{}',
    brands JSONB DEFAULT '{}',
    fotos JSONB DEFAULT '[]',
    desvios JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours'),
    INDEX (telefono),
    INDEX (expires_at)
);
```

---

## 🔄 Paso 5: Actualizar main.py webhook

**En `main.py` línea ~956**, modificar:

```python
# ANTES:
result = await route.handle_message(payload, meta_client)

# DESPUÉS:
# Try new perfumery audit flow first
session = get_session(payload.telefono)
if session and session.estado != AuditState.DONE:
    result = await route.handle_perfumeria_audit(payload, meta_client)
elif payload.tipo == "text" and any(word in payload.contenido.lower() for word in ["perfumeria", "auditar"]):
    result = await route.handle_perfumeria_audit(payload, meta_client)
else:
    result = await route.handle_message(payload, meta_client)
```

---

## ⚙️ Testing Inicial

### Manual Test via WhatsApp

1. **Iniciar auditoría**:
   ```
   Auditor: "auditar perfumeria"
   Bot: "¿ID de sucursal? (SC-001)"
   ```

2. **Enviar ID sucursal**:
   ```
   Auditor: "SC-001"
   Bot: "✓ Auditoría iniciada: SC-001
        Paso 1 de 4: Limpieza...
        Responde: 1-5"
   ```

3. **Responder puntuación**:
   ```
   Auditor: "4"
   Bot: "✓ Limpieza: 4/5
        Siguiente: Stock..."
   ```

4. **Completar scoring**:
   ```
   Auditor: "3" → Stock
   Auditor: "2" → Ofertas (mueve a BRANDS)
   Bot: "Ofertas: 2/5. Marca 1/4: Unilever..."
   Auditor: "3" → Unilever
   [Continua con otras marcas]
   ```

5. **Enviar evidencia**:
   ```
   Auditor: [Envía foto]
   Bot: "✓ Foto recibida. ¿De qué área? (Limpieza, Stock...)"
   Auditor: "Stock"
   Bot: "✓ Guardado. ¿Otra foto?"
   Auditor: "Listo"
   Bot: "RESUMEN: ..."
   ```

6. **Confirmar**:
   ```
   Auditor: "Sí"
   Bot: "✅ Auditoría guardada!"
   ```

---

## 🐛 Debugging

### Check session state
```python
from audit_session import get_session

session = get_session("5493816199195")
print(f"Estado: {session.estado if session else 'None'}")
print(f"Bloques: {session.bloques if session else {}}")
```

### Check memory cache
```python
from audit_session import get_all_sessions

sessions = get_all_sessions()
for s in sessions:
    print(f"{s.telefono}: {s.estado.value}")
```

---

## ✅ Checklist Implementación Fase 1

- [ ] Copiar `audit_session.py` al directorio
- [ ] Copiar `audit_handlers.py` al directorio
- [ ] Agregar imports en `router.py`
- [ ] Agregar método `handle_perfumeria_audit()` en `ConversationRouter`
- [ ] Modificar `_handle_message_locked()` para detectar auditoría v2
- [ ] Modificar webhook en `main.py` (opcional, para nuevo flujo)
- [ ] Compilar y verificar imports: `python -c "from audit_session import *"`
- [ ] Probar con WhatsApp simulado (ver test abajo)

---

## 🧪 Unit Test Script

Guardar como `test_audit_flow.py`:

```python
import asyncio
from audit_session import (
    create_session, get_session, AuditState,
    BloqueType, BLOQUE_ORDER
)
from audit_handlers import AuditConversationHandler
from models import WhatsAppPayload

async def test_basic_flow():
    """Test basic audit flow."""
    
    # 1. Create session
    session = create_session("+5493816199195", "SC-001", "Juan")
    assert session.estado == AuditState.IDLE
    print("✓ Session created")
    
    # 2. Move to SCORING
    session.estado = AuditState.SCORING
    current = session.get_current_bloque()
    assert current == BloqueType.LIMPIEZA.value
    print("✓ First bloque is LIMPIEZA")
    
    # 3. Score a bloque
    session.set_bloque_score(BloqueType.LIMPIEZA.value, 4)
    assert session.bloques[BloqueType.LIMPIEZA.value] == 4
    print("✓ Score saved")
    
    # 4. Move to next
    session.move_to_next_bloque()
    next_bloque = session.get_current_bloque()
    assert next_bloque == BloqueType.STOCK.value
    print("✓ Moved to next bloque")
    
    # 5. Test brand scoring
    session.set_brand_score("unilever", 3)
    assert session.brands[BloqueType.OFERTAS.value]["unilever"] == 3
    print("✓ Brand score saved")
    
    print("\n✅ All basic tests passed!")

if __name__ == "__main__":
    asyncio.run(test_basic_flow())
```

Ejecutar:
```bash
python test_audit_flow.py
```

---

## 🚀 Próxima Fase

Una vez completada la Fase 1, trabajamos en:

**Fase 2: Lógica Scoring Mejorada**
- Mejor validación de entrada
- Manejo de errores más robusto
- Integración con base de datos

**Fase 3: Captura de Evidencia**
- Descarga de fotos desde Meta API
- Validación de calidad de fotos
- Vinculación de fotos a bloques

**Fase 4: Guardado en BD**
- Crear tablas Reporte, Gestion, DesvioEvento
- Notificar gerente automáticamente

---

**Status**: Listo para implementar Fase 1  
**Effort**: ~30 minutos (copiar archivos + agregar métodos)  
**Risk**: Bajo (no modifica código existente, solo agrega métodos nuevos)
