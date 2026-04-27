# Deployment Guide - FarmaAudit

Guía completa para desplegar FarmaAudit en producción.

## Pre-requisitos

- Git instalado
- Node.js 18+ instalado
- Cuenta en Supabase (con tablas creadas)
- Cuenta en un proveedor de hosting (Netlify, Vercel, Railway, etc.)

---

## 1. Preparación

### Backend

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno en backend/.env
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
# (ver SUPABASE_SETUP.md para obtener credenciales)

# Ejecutar localmente para probar
python main.py
```

Verificar que:
- El sync de Sheets→Supabase se ejecuta cada 5 minutos
- No hay errores en logs
- Supabase tiene datos en las tablas

### Frontend

```bash
cd frontend

# Instalar dependencias
npm install

# Configurar .env.local
VITE_SUPABASE_URL=https://tlwglkybxtdtdillljgf.supabase.co
VITE_SUPABASE_ANON_KEY=<tu_anon_key>

# Probar localmente
npm run dev
# Abre http://localhost:5173 y verifica que todo funciona
```

---

## 2. Opciones de Despliegue

### Opción A: Netlify (Recomendado para Frontend)

1. **Conectar repositorio**
   - Ir a https://app.netlify.com
   - Click "New site from Git"
   - Seleccionar tu repositorio

2. **Configurar build**
   ```
   Build command: npm run build
   Publish directory: dist
   ```

3. **Agregar variables de entorno**
   - En Site settings > Build & deploy > Environment
   - Agregar:
     ```
     VITE_SUPABASE_URL=https://...
     VITE_SUPABASE_ANON_KEY=...
     ```

4. **Deploy**
   - Click "Deploy site"
   - Esperar que complete (2-3 min)
   - Tu sitio estará en `https://nombre.netlify.app`

### Opción B: Vercel (Alternativa a Netlify)

1. **Conectar repositorio**
   - Ir a https://vercel.com/new
   - Seleccionar repositorio
   - Importar proyecto

2. **Configurar**
   - Framework: Vite
   - Build command: `npm run build`
   - Output directory: `dist`

3. **Variables de entorno**
   - En Project Settings > Environment Variables
   - Agregar VITE_* variables

4. **Deploy**
   - Click "Deploy"

### Opción C: Railway (Backend + Frontend)

#### Frontend

1. **Conectar repositorio**
   - Ir a https://railway.app
   - Click "New Project"
   - Seleccionar "Deploy from GitHub repo"

2. **Configurar**
   - Service: Node.js
   - Build command: `npm run build`
   - Start command: `npm run preview` (para serve estático)
   - Port: 3000

3. **Agregar variables**
   ```
   VITE_SUPABASE_URL=...
   VITE_SUPABASE_ANON_KEY=...
   ```

4. **Deploy**

#### Backend

1. **Conectar repositorio**
   - Nuevo servicio en el mismo proyecto Railway
   - Python

2. **Configurar**
   - Root directory: `/` (raíz del repo)
   - Start command: `python main.py`
   - PORT variable: `8000`

3. **Agregar variables**
   ```
   SUPABASE_URL=...
   SUPABASE_SERVICE_KEY=...
   ANTHROPIC_API_KEY=...
   META_PHONE_NUMBER_ID=...
   META_ACCESS_TOKEN=...
   META_VERIFY_TOKEN=...
   GOOGLE_SHEETS_ID=...
   GOOGLE_SERVICE_ACCOUNT_JSON=...
   GOOGLE_DRIVE_FOLDER_ID=...
   HOST=0.0.0.0
   PORT=8000
   ```

4. **Configurar CORS en backend**
   - En `main.py`, agregar:
     ```python
     from fastapi.middleware.cors import CORSMiddleware
     
     app.add_middleware(
         CORSMiddleware,
         allow_origins=["https://tu-frontend.railway.app"],
         allow_methods=["*"],
         allow_headers=["*"],
     )
     ```

---

## 3. Post-Deploy: Verificaciones

- [ ] Frontend carga sin errores
- [ ] Login funciona
- [ ] Dashboard muestra datos
- [ ] Tablas de sucursales/reportes cargan
- [ ] RLS filtra datos correctamente
- [ ] No hay errores en console (DevTools > Console)
- [ ] Network requests exitosos (DevTools > Network)

---

## 4. Mantenimiento Continuo

### Monitoreo

**Frontend**
- Netlify Analytics (si está activado)
- Vercel Analytics (si está activado)
- Google Analytics (opcional - agregar script)

**Backend**
- Railway Logs (Si está en Railway)
- CloudWatch / Datadog (si agrega monitoring externo)
- Revisar logs de APScheduler cada mañana

### Actualizaciones

```bash
# Actualizar dependencias (dev)
npm outdated      # Ver qué está desactualizado
npm update         # Actualizar

# Actualizar Supabase schema (SQL)
# Ejecutar en Supabase > SQL Editor si hay cambios

# Re-desplegar backend (Railway)
# Simplemente hacer push a main/master
```

### Backups

- **Google Sheets**: Mantiene historial automático
- **Supabase**: Realiza backups automáticos (plan gratuito: 7 días, plan pro: 30 días)

---

## 5. Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| "VITE_SUPABASE_URL not found" | Vars de env no configuradas | Agregar en platform de hosting |
| Login falla con "invalid API key" | ANON_KEY incorrecta | Copiar nuevamente de Supabase > API |
| "Access denied" al cargar datos | RLS bloqueando | Verificar RLS policies en Supabase |
| Datos desactualizados | Backend no está sincronizando | Revisar logs del backend, reiniciar |
| CORS error en network | Frontend Origin no en whitelist del backend | Actualizar CORS en main.py |

---

## 6. Dominio Personalizado (Opcional)

### Netlify
1. Comprar dominio o apuntar el tuyo
2. En Site settings > Domain management
3. Seguir instrucciones de DNS

### Vercel
1. En Project settings > Domains
2. Agregar tu dominio
3. Configurar DNS según instrucciones

### Railway
1. En Environment settings
2. Agregar variable `RAILWAY_ENVIRONMENT_NAME=production`
3. Vercel o Netlify pueden actuar como CDN

---

## 7. Seguridad

- [ ] `SUPABASE_SERVICE_KEY` nunca en repos públicos (solo en backend .env)
- [ ] CORS configurado correctamente
- [ ] RLS policies activadas en Supabase
- [ ] HTTPS activado (automático en Netlify/Vercel/Railway)
- [ ] Rate limiting en backend (si necesario)
- [ ] Secrets rotados regularmente

---

## 8. Rollback (en caso de problema)

**Netlify**
- Site deployments > seleccionar versión anterior > "Publish deploy"

**Vercel**
- Deployments > click en versión anterior > "Promote to Production"

**Railway**
- Seleccionar release anterior en la lista de deployments

---

## Soporte

En caso de problemas:
1. Revisar logs (DevTools > Console, o panel de hosting)
2. Verificar variables de entorno
3. Revisar que Supabase tiene datos
4. Reiniciar el servicio (Redeploy)

¡Frontend listo para producción! 🚀
