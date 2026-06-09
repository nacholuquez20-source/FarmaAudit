# WhatsApp Audit Flow - Conversación Conversacional

**Status**: 🔧 En diseño  
**Focus**: Backend conversacional (router.py + main.py)  
**Scope**: 
- ✅ Flujo conversacional paso a paso
- ✅ Captura de fotos con validación
- ✅ Sub-puntos por marca (OFERTAS)
- ✅ Resumen + guardado en BD

---

## 📱 Flujo Conversacional Actual vs Mejorado

### ACTUAL (Audit libre)
```
Auditor: "Buenos días"
Bot: "Hola Juan, ¿qué desvíos encontraste hoy?"
Auditor: "Polvo en la vidriera y falta stock de X"
Bot: [Procesa audio/Claude] → Crea reporte
```

### MEJORADO (Auditoría Perfumería Estructurada)
```
[1] Bot: "Hola Juan. Vamos a auditar Farmacia Centro"
    Bot: "Paso 1: Califica LIMPIEZA (1-5)"

[2] Auditor: "4"
    Bot: "✓ Limpieza: 4/5"
    Bot: "Paso 2: Califica STOCK (1-5)"

[3] Auditor: "3"
    Bot: "⚠️ Stock: 3/5 - Hay problemas. Espero fotos"
    Bot: "Paso 3: Califica OFERTAS (1-5)"

[4] Auditor: "2"
    Bot: "⚠️ Ofertas: 2/5 - Desglose por marca:"
    Bot: "  • Unilever (1-5)?"

[5] Auditor: "3"
    Bot: "✓ Unilever: 3/5"
    Bot: "  • Colgate (1-5)?"

[6] Auditor: "2"
    Bot: "✓ Colgate: 2/5"
    [Continua Haleon, Genomma...]

[7] Bot: "Ahora envia fotos de:"
    Bot: "  ✓ Stock bajo"
    Bot: "  ✓ Ofertas desordenadas"

[8] Auditor: [Envía foto 1]
    Bot: "✓ Foto recibida. Puedes agregar descripción:"

[9] Auditor: "Falta reposición en Stock"
    Bot: "✓ Guardado. ¿Otra foto?"

[10] Auditor: [Envía foto 2]
     Bot: "✓ Foto recibida..."

[11] Auditor: "Listo"
     Bot: "RESUMEN:"
         "Limpieza: 4/5 ✓"
         "Stock: 3/5 ⚠️ (1 foto)"
         "Ofertas: 2/5 ⚠️ (1 foto)"
         "Burbujas: ? (pendiente)"
         "¿Confirmas?"

[12] Auditor: "Sí"
     Bot: "✓ Auditoría guardada. Gerente notificado."
```

---

## 🔧 Componentes a Crear/Modificar

### 1. **AuditSession State Machine** (router.py)

```python
class AuditSession:
    """Sesión de auditoría en progreso"""
    
    id_sesion: str                    # audit_XXX
    telefono: str                     # Auditor phone
    sucursal_id: str                  # SC-001
    estado: AuditState                # SCORING | EVIDENCE | SUMMARY | DONE
    
    # Scoring
    bloques: Dict[str, int]           # {'LIMPIEZA': 4, 'STOCK': 3, ...}
    brands: Dict[str, Dict[str, int]] # {'OFERTAS': {'unilever': 3, ...}}
    
    # Evidence
    fotos: List[FotoEvidence]
    desvios: List[Desvio]
    
    # Timestamps
    created_at: datetime
    started_at: datetime
    current_bloque: str               # LIMPIEZA
    current_brand: Optional[str]      # 'unilever'
```

### 2. **Message Handler por Estado** (router.py)

```python
class ConversationRouter:
    
    async def handle_message(payload, meta_client):
        """Route based on conversation state"""
        
        session = get_audit_session(payload.telefono)
        
        if session.estado == AuditState.IDLE:
            → handle_init(payload)         # Inicia auditoría
        
        elif session.estado == AuditState.SCORING:
            → handle_score(payload)        # Recibe 1-5
        
        elif session.estado == AuditState.EVIDENCE:
            → handle_evidence(payload)     # Recibe foto/texto
        
        elif session.estado == AuditState.SUMMARY:
            → handle_confirmation(payload) # Sí/No
```

---

## 🎯 Estados Conversacionales

### STATE 1: INIT (Inicialización)

**Trigger**: Auditor escribe o inicia chat  
**Bot responde**:
```
"Hola Juan 👋"
"Vamos a auditar Farmacia Centro"
"Puntúa cada área de 1 (Muy malo) a 5 (Excelente)"
"Paso 1: LIMPIEZA (estado de góndolas, orden, polvo)"
"⏳ Responde: 1, 2, 3, 4 o 5"
```

**Next state**: SCORING (LIMPIEZA)

---

### STATE 2: SCORING (Puntuación de áreas)

**Current**: Esperando número 1-5  
**Variables**: `session.current_bloque = "LIMPIEZA"`

**Auditor responde**: "4"

**Validación**:
```python
if not mensaje.isdigit() or not 1 <= int(mensaje) <= 5:
    → "❌ Por favor responde 1, 2, 3, 4 o 5"
    → (No cambia estado)
```

**Si válido**: "4"

**Bot procesa**:
```python
session.bloques['LIMPIEZA'] = 4
session.current_bloque = 'STOCK'

# Si es OFERTAS, pasa a SCORING_BRANDS
if current == 'OFERTAS':
    session.estado = AuditState.SCORING_BRANDS
    session.current_brand = 'unilever'
    
    respuesta = "✓ Ofertas: 2/5\n\nDESGLOSE POR MARCA:\n• Unilever (exhibición, disponibilidad)"
else:
    respuesta = f"✓ Limpieza: 4/5\n\nSiguiente: Stock (1-5)?"
```

**Envía**: 
```
"✓ Limpieza: 4/5"
"Siguiente: STOCK & Inventario"
"(Niveles, productos vencidos, reposición)"
"Responde: 1-5"
```

**Next state**: SCORING (STOCK) o SCORING_BRANDS

---

### STATE 3: SCORING_BRANDS (Sub-puntos de OFERTAS)

**Current**: Esperando número para marca  
**Variables**: 
```python
session.current_bloque = 'OFERTAS'
session.current_brand = 'unilever'
```

**Flujo**:
```
Bot: "OFERTAS: Marca 1/4 - Unilever"
     "(Exhibición, disponibilidad, precios)"
     "Responde: 1-5"

Auditor: "3"

Bot: "✓ Unilever: 3/5"
     "Marca 2/4 - Colgate-Palmolive"
     "Responde: 1-5"

Auditor: "2"

Bot: "✓ Colgate: 2/5 ⚠️"
     "Marca 3/4 - Haleon"
     "Responde: 1-5"

[Continua...]

[Después de 4 marcas]

Bot: "✓ Genomma: 4/5"
     "OFERTAS completada: Promedio 3/5"
     "Siguiente: BURBUJAS & Señalización"
```

**Next state**: SCORING (BURBUJAS) o EVIDENCE

---

### STATE 4: EVIDENCE (Captura de evidencia)

**Bot dice**:
```
"Ahora necesito fotos de los problemas encontrados"
"Encontré problemas en:"
"  ✓ Stock (3/5)"
"  ✓ Ofertas (2/5)"

"Por favor envía fotos de:"
"  📷 Stock bajo / faltantes"
"  📷 Ofertas desordenadas"

"Puedes enviar fotos o escribir 'Listo' cuando termines"
```

**Si Auditor envía FOTO**:
```python
tipo = 'image'
media_id = payload.media_id

# Descargar foto desde Meta
media_url = await _get_meta_media_url(media_id)

# Validar que sea foto real (no blurry, etc)
validation = await validate_photo(media_url)

session.fotos.append({
    'url': media_url,
    'timestamp': now(),
    'bloque': 'STOCK'  # Inferir de contexto
})

respuesta = "✓ Foto recibida. ¿De qué área es?"
```

**Si Auditor escribe texto**:
```
Auditor: "Falta reposición de Stock"
Bot: "✓ Guardado: Falta reposición de Stock"
     "¿Otra foto?"
```

**Si Auditor escribe "Listo"**:
```
session.estado = AuditState.SUMMARY
```

**Next state**: EVIDENCE (más fotos) o SUMMARY

---

### STATE 5: SUMMARY (Resumen final)

**Bot muestra**:
```
"RESUMEN DE AUDITORÍA"

"📍 Farmacia Centro"
"⏰ 2026-06-03 14:30"

"PUNTUACIONES:"
"  Limpieza:   4/5 ✓"
"  Stock:      3/5 ⚠️ (2 fotos)"
"  Ofertas:    2/5 ⚠️ (1 foto)"
"    ├─ Unilever:        3/5"
"    ├─ Colgate:         2/5 ⚠️"
"    ├─ Haleon:          4/5 ✓"
"    └─ Genomma:         4/5 ✓"
"  Burbujas:   5/5 ✓"

"DESVÍOS: 3"
"  • Stock bajo"
"  • Ofertas desordenadas"
"  • Colgate con baja exposición"

"¿Confirmas envio? (Sí/No)"
```

**If "Sí"**:
```python
# Guardar en BD
await save_audit_session(session)
# Crear Reporte, Gestion, DesvioEvento
await create_audit_records(session)
# Notificar gerente
await notify_manager(session.sucursal_id)

respuesta = "✓ Auditoría guardada!\nGerente notificado."
session.estado = AuditState.DONE
```

**If "No"**:
```python
respuesta = "Entendido. ¿Qué quieres cambiar?"
session.estado = AuditState.EDIT
```

**Next state**: DONE

---

## 📁 Archivos a Modificar/Crear

```
router.py (MODIFICAR)
├─ Agregar AuditSession class
├─ Agregar state machine para auditoría perfumería
├─ Métodos:
│  ├─ handle_score()
│  ├─ handle_brands_score()
│  ├─ handle_evidence()
│  ├─ handle_summary()
│  └─ validate_score()

audit_session.py (CREAR)
├─ class AuditSession
├─ class AuditState (IDLE, SCORING, SCORING_BRANDS, EVIDENCE, SUMMARY, DONE)
├─ class BrandScore
└─ helpers para persistencia

meta_client.py (POSIBLE MEJORA)
├─ Método para descargar fotos
├─ Método para validar fotos
└─ Templates de mensajes estructurados
```

---

## 💾 Persistencia de Sesión

### Opción A: Redis (rápido, temporal)
```python
# Guardar sesión en Redis por 24h
await redis.setex(
    f"audit_session:{telefono}",
    86400,
    json.dumps(session.dict())
)
```

### Opción B: Supabase (permanente)
```python
# Nueva tabla: audit_sessions_pending
client.table("audit_sessions_pending").insert({
    'id_sesion': 'audit_XXX',
    'telefono': '+549...',
    'sucursal_id': 'SC-001',
    'estado': 'SCORING',
    'bloques': {'LIMPIEZA': 4, ...},
    'brands': {'OFERTAS': {'unilever': 3, ...}},
    'created_at': now(),
    'expires_at': now() + 24h
})
```

**Recomendación**: Combinado (Redis para rapidez + Supabase como respaldo)

---

## 🔄 Flujo Técnico Completo

```
1. Auditor envía mensaje a WhatsApp
   ↓
2. Webhook recibe en main.py:850-970
   ↓
3. ConversationRouter.handle_message(payload, meta_client)
   ↓
4. get_audit_session(telefono)
   ├─ ¿Existe en Redis? → Cargar
   └─ ¿No existe? → Nueva sesión (IDLE)
   ↓
5. Switch por session.estado:
   ├─ IDLE → handle_init()
   ├─ SCORING → validate_score() → handle_score()
   ├─ SCORING_BRANDS → validate_brand_score() → handle_brands_score()
   ├─ EVIDENCE → validate_evidence() → handle_evidence()
   ├─ SUMMARY → handle_confirmation()
   └─ DONE → "Gracias, auditoría completada"
   ↓
6. Guardar sesión actualizada en Redis
   ↓
7. Enviar respuesta a auditor via meta_client.send_text()
   ↓
8. Return {"status": "ok"} a Meta
```

---

## 📋 Checklist Implementación

### Fase 1: Estructura Base
- [ ] Crear `audit_session.py` con clases
- [ ] Crear `AuditState` enum
- [ ] Crear tabla `audit_sessions_pending` en Supabase

### Fase 2: Router Logic
- [ ] Implementar `handle_init()`
- [ ] Implementar `handle_score()`
- [ ] Implementar `handle_brands_score()`
- [ ] Implementar validación de números 1-5

### Fase 3: Evidence
- [ ] Implementar `handle_evidence()`
- [ ] Descargar fotos desde Meta API
- [ ] Validar calidad de fotos
- [ ] Vincular fotos a bloques

### Fase 4: Resumen & Guardado
- [ ] Implementar `handle_summary()`
- [ ] Generar resumen formateado
- [ ] Crear `save_audit_session()` → Gestion + Reporte
- [ ] Notificar gerente

### Fase 5: Testing
- [ ] Test mensajes válidos (1-5)
- [ ] Test mensajes inválidos
- [ ] Test fotos
- [ ] Test sesión persistencia
- [ ] Test completar auditoría end-to-end

---

## 🎯 Mensajes Bot (Templates)

```python
MESSAGES = {
    'INIT': """
Hola {auditor_nombre} 👋

Vamos a auditar {sucursal_nombre}
Puntúa cada área de 1 (Muy malo) a 5 (Excelente)

Paso 1: LIMPIEZA & Organización
(Estado de góndolas, orden general, polvo)

Responde: 1, 2, 3, 4 o 5
    """,
    
    'SCORE_OK': "✓ {bloque}: {score}/5",
    'SCORE_ERROR': "❌ Por favor responde 1, 2, 3, 4 o 5",
    
    'BRAND_SCORE': "{marca} (1-5)?",
    
    'EVIDENCE_PROMPT': """
Ahora necesito fotos de los problemas:
{problemas}

Envía fotos o escribe 'Listo'
    """,
    
    'PHOTO_OK': "✓ Foto recibida. ¿De qué área es?",
    
    'SUMMARY': """
RESUMEN
{tabla_puntuaciones}
{lista_desvios}
¿Confirmas? (Sí/No)
    """,
    
    'CONFIRMATION_OK': "✓ Auditoría guardada! Gerente notificado.",
}
```

---

**Next**: Implementar Fase 1 (estructura base)

