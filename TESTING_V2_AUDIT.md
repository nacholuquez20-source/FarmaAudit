# Testing WhatsApp Audit v2

## Quick Start

### Prerequisites
- Active WhatsApp account linked to auditor
- Sucursal in the system (e.g., SC-001, SC-002, etc.)
- Phone number registered as auditor
- Meta WhatsApp Cloud API access

### Test Flow

**Step 1: Select Sucursal**
```
Send to bot: SC-001
```
Response: Welcome message with "Paso 1 de 4: Limpieza 🧹"

**Step 2: Score Each Bloque**
```
Send: 4  (for Limpieza)
```
Response: "Documenta lo que observas... (fotos, audios, textos)"

**Step 3: Collect Evidence (Any Order)**

Option A - Text note:
```
Send: "Gondola desorganizada, falta reposición"
```
Response: "✓ Nota guardada en Limpieza"

Option B - Photo:
```
Send: [Image file]
```
Response: "✓ Foto guardada en Limpieza"

Option C - Audio:
```
Send: [Voice message]
```
Response: "✓ Audio guardado en Limpieza"

**Step 4: Move to Next Bloque**
```
Send: SIGUIENTE
```
Response: "✓ Limpieza completado! ... Paso 2 de 4: Stock 📦"

**Step 5: Repeat for All Bloques**
- LIMPIEZA (1/4)
- STOCK (2/4)
- OFERTAS (3/4) - includes brand breakdown
- BURBUJAS (4/4)

**Step 6: Review Summary**
After all evidence for last bloque, system shows:
```
📋 RESUMEN DE AUDITORÍA
📍 Sucursal: SC-001
⏰ 09/06/2026 14:30

📊 PUNTUACIONES:
  Limpieza & Organización: 4/5
  Stock & Inventario: 4/5
  Ofertas & Exhibición: 4/5
    • Unilever: 4/5
    • Colgate-Palmolive: 4/5
    • Haleon: 4/5
    • Genomma Lab: 4/5
  Displays & Señalización: 4/5

⚠️ DESVÍOS ENCONTRADOS (2):
  • Gondola desorganizada
  • Falta señalización en estantes

📷 FOTOS: 3

¿Confirmas envío?
1. Sí, enviar
2. No, editar
```

**Step 7: Confirm**
```
Send: 1  (or "sí", "yes", "ok")
```
Response:
```
✅ ¡Auditoría guardada!

ID: audit_1781034026
Fotos: 3
Desvíos: 2

Gerente notificado de 2 hallazgo(s)
```

---

## Expected Behaviors

### ✅ Correct Behaviors

- Score must be 1-5 (rejects 0, 6, letters, etc.)
- Photos must be ≥320x320, <10MB, not blurry
- Text, audio, and photos can be sent in any order
- SIGUIENTE advances to next bloque (case-insensitive)
- All evidence is linked to correct bloque
- Summary shows all scores and desvios
- Manager receives notification

### ❌ Error Cases (Should Be Handled)

1. **Invalid score**: "❌ Por favor responde 1, 2, 3, 4 o 5"
2. **Blurry photo**: "❌ Foto borrosa. Intenta de nuevo o escribe 'SIGUIENTE'"
3. **Too small photo**: "❌ Foto muy pequeña (< 320x320)"
4. **Too large photo**: "❌ Archivo muy grande (> 10MB)"
5. **Invalid format**: "❌ Formato no soportado"
6. **Network error**: "❌ Error descargando foto. Intenta de nuevo"

---

## Logging to Monitor

Look for these log messages to verify flow:

```
[INFO] Created v2 audit session audit_XXXXX for +PHONE in SCORING state
[INFO] Sent welcome message for v2 session audit_XXXXX
[INFO] Score received for LIMPIEZA: 4
[INFO] Downloaded and validated photo for LIMPIEZA
[INFO] Moved to BLOQUE_EVIDENCE_COLLECTION
[INFO] SIGUIENTE keyword detected, moving to next bloque
[INFO] Session transitioned to SUMMARY
[INFO] Audit session audit_XXXXX saved to database
[INFO] Manager notification sent
```

---

## Database Verification

After audit completes:

### Check Reporte Table
```sql
SELECT * FROM reporte 
WHERE sucursal_id = 'SC-001' 
ORDER BY created_at DESC 
LIMIT 1;
```

Expected columns:
- `id`: UUID
- `sucursal_id`: SC-001
- `auditor_id`: Auditor phone
- `puntuacion_promedio`: Average of all bloque scores
- `estado`: COMPLETADO
- `fecha_audit`: Timestamp

### Check Gestion Table
```sql
SELECT * FROM gestion 
WHERE reporte_id = 'REPORTE_ID'
ORDER BY created_at;
```

Expected: One record per desvio found

### Check DesvioEvento Table
```sql
SELECT * FROM desvio_evento 
WHERE reporte_id = 'REPORTE_ID'
ORDER BY timestamp;
```

Expected: Full audit trail with timestamps

---

## Common Issues & Solutions

### Issue: "Auditoría iniciada" but session not in SCORING
**Solution**: Check that router.py line 2216 sets `estado = AuditState.SCORING`

### Issue: Photo uploaded but validation fails
**Solution**: 
- Check photo is ≥320x320
- Ensure photo is in focus (Laplacian variance > 80)
- Verify file size < 10MB
- Check MIME type is image/jpeg or image/png

### Issue: SIGUIENTE doesn't advance to next bloque
**Solution**: 
- Verify text is exactly "SIGUIENTE" (case-insensitive OK)
- Check session.move_to_next_bloque() returns True
- Verify state machine transitions (line 223 in audit_handlers.py)

### Issue: Manager not getting notification
**Solution**:
- Verify sucursal has manager phone in database
- Check MetaClient.send_text() method
- Verify send_manager_notification() is called (line 590)

---

## Test Checklist

- [ ] Can start audit with sucursal ID
- [ ] Welcome message shows correct bloque
- [ ] Can score 1-5
- [ ] Invalid scores rejected
- [ ] Can send photos
- [ ] Can send text notes
- [ ] Can send audio
- [ ] Photos are validated
- [ ] Evidence linked to correct bloque
- [ ] SIGUIENTE moves to next bloque
- [ ] All 4 bloques can be scored
- [ ] OFERTAS shows brand breakdown
- [ ] Summary is correct
- [ ] Can confirm audit
- [ ] Reporte created in DB
- [ ] Gestion created for each desvio
- [ ] Manager notification sent

---

## Expected Result

After following the complete flow:
1. Session moves through all 6 states
2. All evidence is collected and stored
3. Summary shows complete audit info
4. Audit confirmed and marked DONE
5. Database records created
6. Manager notified via WhatsApp
7. Session cleaned up (can start new audit)

**Time**: ~5-10 minutes to complete one full audit
