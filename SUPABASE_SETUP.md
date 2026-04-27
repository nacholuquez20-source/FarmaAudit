# Supabase Setup Guide

## Overview
Hemos configurado un **sync automático** que sincroniza datos de Google Sheets → Supabase cada 5 minutos:

```
WhatsApp Bot → Google Sheets → [FastAPI Sync Job] → Supabase ← Frontend React
```

---

## Pasos de Configuración

### 1. Crear tablas en Supabase ✓ (SQL)

**Abre Supabase Dashboard:**
- Ve a: https://tlwglkybxtdtdillljgf.supabase.co
- Navega a **SQL Editor**
- Crea una nueva consulta
- **Copia TODO el contenido de `supabase_setup.sql`** y pégalo
- Ejecuta (Run)

Esto crea:
- `sucursales` (maestro de farmacias)
- `reportes` (hallazgos de auditorías)
- `gestion` (planes de acción)
- `auditores` (maestro de auditores)
- `control_stock` (verificaciones de stock)
- `profiles` (usuarios con roles)
- **RLS Policies** (seguridad por rol)
- **Índices** (para performance)

---

### 2. Obtener credenciales Supabase

**ANON KEY (para frontend):**
1. Ve a **Settings → API**
2. Copia `anon public` (la clave pública, es segura compartir)
3. Pega en `frontend/.env.local`:
   ```
   VITE_SUPABASE_URL=https://tlwglkybxtdtdillljgf.supabase.co
   VITE_SUPABASE_ANON_KEY=<PEGA_AQUI>
   ```

**SERVICE KEY (para backend sync):**
1. Ve a **Settings → API**
2. Copia `service_role secret` (⚠️ SENSIBLE - nunca a git/público)
3. Pega en `backend/.env`:
   ```
   SUPABASE_URL=https://tlwglkybxtdtdillljgf.supabase.co
   SUPABASE_SERVICE_KEY=<PEGA_AQUI>
   ```

---

### 3. Instalar dependencias backend

```bash
pip install supabase
```

---

### 4. Crear usuario admin

Desde Supabase Dashboard:

1. Ve a **Authentication → Users**
2. Click **+ Create user**
3. Email: `admin@farmaaudit.com` (o tu email)
4. Password: genera una segura
5. Click **Create user**

Luego, en **SQL Editor**, ejecuta:
```sql
-- Actualizar perfil del usuario admin
UPDATE profiles 
SET role = 'admin', nombre = 'Admin'
WHERE id = (SELECT id FROM auth.users WHERE email = 'admin@farmaaudit.com')
LIMIT 1;
```

---

### 5. Verificar sincronización

1. **Inicia el backend**: `python main.py`
2. **Observa logs** (busca `===== Starting full Sheets → Supabase sync =====`)
3. El sync corre automáticamente cada 5 minutos
4. En Supabase, ve a **Table Editor** y revisa que hay datos en:
   - `sucursales`
   - `reportes`
   - `gestion`
   - `auditores`

Si hay errores, check:
- ¿SUPABASE_URL y SUPABASE_SERVICE_KEY están en `.env`?
- ¿Google Sheets está accesible y tiene datos?
- ¿`supabase-py` está instalado?

---

### 6. Probar frontend

```bash
cd frontend
npm run dev
```

Navega a http://localhost:5173

**Testing:**
1. Login con `admin@farmaaudit.com` / tu password
2. Verifica que ves datos en:
   - Dashboard (KPIs)
   - Sucursales (tabla)
   - Admin (auditores)
3. Los datos son los mismos de Google Sheets (via sync)

---

## Seguridad: Row Level Security (RLS)

El SQL que ejecutaste incluye **RLS Policies** que aseguran:

| Tabla | Admin | Auditor |
|-------|-------|---------|
| `sucursales` | ✓ Lee todos | ✓ Lee todos |
| `reportes` | ✓ Lee todos | ✓ Solo los suyos (filtrado por teléfono) |
| `gestion` | ✓ Lee y edita | ✓ Solo lee todos |
| `auditores` | ✓ Lee, crea, edita | ✗ No ve |
| `control_stock` | ✓ Lee todos | ✓ Solo los suyos |

Supabase **automáticamente** filtra basado en `auth.uid()` y `role`.

---

## Troubleshooting

**❌ "SUPABASE_URL and SUPABASE_SERVICE_KEY not found"**
- Check `.env` tiene las variables sin espacios
- Restart backend

**❌ Datos no sincronizados después de 5 min**
- Ve a Supabase > Settings > API, verifica credenciales
- Check logs de FastAPI para errores
- Verifica que Google Sheets tiene datos

**❌ Frontend login falla**
- Verifica `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` en frontend/.env.local
- Check que el usuario existe en Supabase > Authentication

**❌ Auditor ve datos de otros auditores**
- RLS no está activado correctamente
- Re-ejecuta el SQL desde `supabase_setup.sql`
- Verifica que `profiles.telefono` coincide con `reportes.auditor`

---

## Próximos pasos

1. ✅ Tablas Supabase creadas
2. ✅ Frontend lee desde Supabase (no FastAPI)
3. ✅ Backend sincroniza cada 5 min
4. ✅ RLS asegura datos privados

**Ya puedes:**
- ✓ Login con Supabase
- ✓ Ver datos filtrados por rol
- ✓ Editar Gestion (admin)
- ✓ Gestionar auditores (admin)

**Pendiente (future):**
- WhatsApp image display (cuando sea necesario)
- Charts avanzados (Recharts ya instalado)
- Email de resúmenes (SendGrid opcional)
