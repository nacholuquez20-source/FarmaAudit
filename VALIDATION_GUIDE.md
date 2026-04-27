# Loop Fix Validation Guide

## Pre-Deployment Validation (Local)

### 1. Code Review
```bash
# Check modified files for syntax errors
python -m py_compile main.py router.py sheets.py

# Output should be clean (no errors)
```

### 2. Run Unit Tests
```bash
# Install pytest if needed
pip install pytest pytest-asyncio

# Run deduplication tests
cd /c/Users/jluqu/OneDrive/Desktop/FarmaAudit
pytest test_dedup.py -v --tb=short

# Expected: 5 tests passing
# ✓ test_message_deduplication
# ✓ test_concurrent_messages_same_auditor
# ✓ test_concurrent_messages_different_auditors
# ✓ test_concurrent_processing_blocked
# ✓ test_message_dedup_ttl_expiry
```

### 3. Lint Check (optional but recommended)
```bash
# Check code style
pip install pylint
pylint main.py router.py sheets.py --disable=all --enable=E,F

# Should show 0 errors
```

---

## Deployment Validation (Railway)

### 1. Deploy Code
```bash
git add -A
git commit -m "Fix: Prevent message loop with dedup, locks, and atomic updates"
git push origin master

# Railway auto-deploys on main branch
# Wait 2-3 minutes for build & deploy
```

### 2. Health Check
```bash
# Verify service is up
curl https://your-railway-url/health

# Expected response:
# {"status":"healthy","timestamp":"2026-04-27T..."}
```

### 3. Tail Logs
```bash
# Watch logs during test
railway logs --follow

# Or use Dashboard > Logs tab
```

---

## Manual QA Scenarios

### Scenario A: Single Normal Message (Baseline)

**Setup**:
- Use WhatsApp test account or manual Meta API call
- Auditor phone: `549XXXXXXXXXX` (registered)

**Test Steps**:
```
1. Send message: "Hallazgo en Farmacia A, Perfumería, Desorden, Baja"
2. Expected response: "✅ Borrador de Hallazgos - ¿Confirmo?"
3. Check Sheets > Conversaciones: estado = esperando_confirmacion
4. Check Sheets > Pendientes: 1 row created
5. Respond: "SI"
6. Expected: "✅ Hallazgos guardados. Notificaciones enviadas..."
7. Check Sheets > Reportes: 1 row created
8. Check Sheets > Gestiones: 1 row created
```

**Log Evidence**:
```
[abc123] Received message from 549XXXXXXXXXX (type: text, msg_id: wamid.XXX)
[abc123] Processed message result: parse_success
[abc123] Confirmation response from 549XXXXXXXXXX: 'SI'
[abc123] Processed message result: confirmed
```

**✅ Pass Criteria**: Exactly 1 report and 1 gestion created

---

### Scenario B: Duplicate Webhook (Deduplication Test)

**Setup**:
- Intercept and replay Meta webhook payload

**Test Steps**:
```
1. Send message via WhatsApp: "Hallazgo X"
2. Capture webhook request from logs
3. Replay same webhook 3 times within 30 seconds
4. Verify responses
```

**Expected Logs**:
```
[xyz789] Received message from 549XXXXXXXXXX (type: text, msg_id: wamid.YYY)
[xyz789] Processed message result: parse_success
[aaa111] Received message from 549XXXXXXXXXX (type: text, msg_id: wamid.YYY)
[aaa111] Duplicate message detected (msg_id: wamid.YYY, phone: 549XXXXXXXXXX). Skipping.
[aaa111] Processed message result: duplicate_skipped
[bbb222] Received message from 549XXXXXXXXXX (type: text, msg_id: wamid.YYY)
[bbb222] Duplicate message detected (msg_id: wamid.YYY, phone: 549XXXXXXXXXX). Skipping.
[bbb222] Processed message result: duplicate_skipped
```

**Sheets Verification**:
```
- Pendientes sheet: Still 1 row (not 3)
- Reportes sheet: Still 0-1 rows (not 3)
```

**✅ Pass Criteria**: Only first webhook processed, duplicates skipped

---

### Scenario C: Concurrent Messages (Lock Test)

**Setup**:
- Use Apache JMeter or custom script to send concurrent requests
- Two messages for SAME auditor, <100ms apart

**Test Script** (curl):
```bash
#!/bin/bash
WEBHOOK_URL="https://your-railway-url/webhook"
PAYLOAD='{"entry":[{"changes":[{"value":{"messages":[{"id":"msg_001","from":"5491234567890","type":"text","text":{"body":"Hallazgo A"}}]}}]}]}'

# Send two requests concurrently
curl -X POST $WEBHOOK_URL -H "Content-Type: application/json" -d "$PAYLOAD" &
curl -X POST $WEBHOOK_URL -H "Content-Type: application/json" -d "$PAYLOAD" &
wait
```

**Expected Logs** (in order):
```
[ccc333] Received message from 5491234567890 (..., msg_id: msg_001)
[ccc333] Processed message result: parse_success
[ddd444] Received message from 5491234567890 (..., msg_id: msg_001)
[ddd444] Duplicate message detected (...). Skipping.

OR (if IDs are different):

[ccc333] Acquired lock for 5491234567890 (lock_acquired_at: 123.45ms)
[ddd444] Waiting for lock on 5491234567890...
[ccc333] Processed message result: parse_success
[ccc333] Released lock for 5491234567890
[ddd444] Acquired lock for 5491234567890 (waited: 234.56ms)
[ddd444] Processed message result: parse_success
[ddd444] Released lock for 5491234567890
```

**Sheets Verification**:
```
- Conversaciones: 1 row, estado = esperando_confirmacion
- Pendientes: 1 row
- NO duplicates
```

**✅ Pass Criteria**: Either dedup catches duplicate IDs, or locks serialize processing

---

### Scenario D: State Update Atomicity

**Setup**:
- Inject transient error in update_conversacion() (optional advanced test)

**Test Steps**:
```
1. Send message that updates conversation
2. Monitor Sheets > Conversaciones for row updates
3. Verify all columns updated at same time
4. Check no partially-updated rows
```

**Expected Behavior**:
```
Row before: estado=idle, id_pendiente="", timestamp="2026-04-27T10:00:00"
Message sent
Row after: estado=esperando_confirmacion, id_pendiente="pend_123", timestamp="2026-04-27T10:00:15"
(All columns update together, no intermediate states visible)
```

**✅ Pass Criteria**: All columns update atomically (no partial updates in logs)

---

### Scenario E: Background Job Limits

**Setup**:
- Monitor background job logs

**Test Steps**:
```
1. Let system run for 30 minutes
2. Check logs for duplicate job execution
3. Verify check_expired_confirmations runs once every N minutes
4. Verify check_expired_audit_sessions runs once every N minutes
```

**Expected Logs** (no duplicates):
```
2026-04-27T10:00:00 - Started timeout_check job
2026-04-27T10:05:00 - Started timeout_check job
2026-04-27T10:10:00 - Started timeout_check job
(One per interval, never two at same time)
```

**Log Antipattern** (would indicate regression):
```
2026-04-27T10:00:00 - Started timeout_check job
2026-04-27T10:00:05 - Started timeout_check job  ← DUPLICATE
```

**✅ Pass Criteria**: Only one job instance running per interval

---

## Regression Testing

### Browser/WhatsApp Manual Test (30 min)

1. **Flow A: Simple Finding**
   - Send: "Hallazgo pequeño en área X"
   - Respond: "SI"
   - Check: 1 reporte + 1 gestion created

2. **Flow B: Edit & Confirm**
   - Send: "Hallazgo con error"
   - Respond: "EDITAR"
   - Send correction: "Corrección..."
   - Respond: "SI"
   - Check: 1 reporte, old pendiente deleted

3. **Flow C: Guided Audit**
   - Send: "INICIO"
   - Select: Sucursal #1
   - Complete 3 blocks
   - Check: Session data saved

4. **Flow D: Stock Verification**
   - Send: "INICIO" → sucursal → STOCK_LOOP → "3"
   - Enter: "Ibuprofeno / 50 / 45"
   - Enter: "Paracetamol / 30 / 30"
   - Enter: "Listo"
   - Check: 2 stock items saved

---

## Metrics to Monitor (24 hours post-deploy)

| Metric | Target | Alert |
|--------|--------|-------|
| Duplicate messages / hour | < 1 | > 5 |
| Duplicate pendientes | 0 | > 0 |
| Failed state updates | < 1 | > 5 |
| Lock wait time (p95) | < 100ms | > 500ms |
| Background job runs | 1/interval | != 1 |
| Webhook errors | < 0.1% | > 1% |

---

## Rollback Checklist

If ANY test fails:

1. [ ] Revert code: `git revert HEAD`
2. [ ] Restart service: `railway redeploy`
3. [ ] Verify health: `curl /health`
4. [ ] Document issue in GitHub issue
5. [ ] Post-mortem: Root cause analysis

---

## Sign-Off Template

**Validator**: _____________  
**Date**: _____________  

- [ ] Unit tests passing
- [ ] Scenario A passed
- [ ] Scenario B passed
- [ ] Scenario C passed
- [ ] Scenario D passed
- [ ] Scenario E passed
- [ ] No regressions observed
- [ ] Ready for production

---

## Questions?

If tests fail:
1. Check logs for error messages
2. Review correlation_id traces
3. Open GitHub issue with logs + steps to reproduce
