# Supabase Migration Guide

## Quick Start

1. Run [`supabase_schema.sql`](supabase_schema.sql) in Supabase SQL Editor.
2. Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env`.
3. Verify the connection with `python -c "from supabase_client import SupabaseManager; SupabaseManager().validate_connection()"`
4. Migrate data with:

```bash
python migrate_sheets_to_supabase.py --table all --confirm
```

## SupabaseManager Example

```python
from supabase_client import SupabaseManager

db = SupabaseManager()
db.validate_connection()

db.upsert_conversacion("5491112345678", estado=ConversationState.IDLE)
auditores = db.list_auditores()
checklist = db.get_checklist_perfumeria_flat()
```

## Data Type Map

| Google Sheets | Supabase | Notes |
| --- | --- | --- |
| Text cell | `text` | Plain strings |
| Yes/No | `boolean` | Stored as `true/false` |
| Date | `date` | UTC date-only when possible |
| Timestamp | `timestamp with time zone` | Always normalized to UTC |
| JSON string | `jsonb` | Parsed before insert |
| Empty cell | `NULL` / default | Depends on column |

## Table Map

| Legacy Sheet | Supabase Table |
| --- | --- |
| `Maestro_Auditores` | `auditores` |
| `Maestro_Sucursales` | `sucursales` |
| `Catalogo_Areas` | `catalogo_areas` |
| `Checklist_Plantillas` | `checklist_plantillas` |
| `Checklist_Perfumeria` | `checklist_perfumeria` |
| `Conversaciones` | `conversaciones` |
| `Pendientes` | `pendientes` |
| `Sesiones_Auditoria` | `sesiones_auditoria` |
| `Reportes` | `reportes` |
| `Gestion` | `gestion` |
| `Resultados_Perfumeria` | `resultados_perfumeria` |
| `Control_Stock` | `control_stock` |

## Rollback

If something goes wrong during the migration, run:

```sql
\i rollback_supabase_migration.sql
```

Or paste the file into Supabase SQL Editor and execute it.
