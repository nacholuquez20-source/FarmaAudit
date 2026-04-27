# FarmaAudit Frontend

Dashboard de gestión de auditorías de farmacias con React, Supabase y Tailwind CSS.

## Stack

- **React 19** + TypeScript
- **Vite** - build tool
- **Supabase** - authentication y database
- **Tailwind CSS** - styling
- **Recharts** - charts
- **React Router v7** - navigation

## Instalación Rápida

### 1. Instalar dependencias

```bash
cd frontend
npm install
```

### 2. Configurar variables de entorno

Crea `frontend/.env.local`:

```
VITE_SUPABASE_URL=https://tlwglkybxtdtdillljgf.supabase.co
VITE_SUPABASE_ANON_KEY=<tu_anon_key>
```

Obtén estos valores desde Supabase:
- Ve a **Settings > API**
- Copia `anon public key`

### 3. Ejecutar dev server

```bash
npm run dev
```

Abre http://localhost:5173

## Estructura

```
src/
├── components/          # Componentes reutilizables
│   └── AppLayout.tsx    # Header y navegación
├── hooks/               # Custom hooks para data fetching
│   ├── useAuth.ts       # Autenticación
│   ├── useSucursales.ts
│   ├── useReportes.ts
│   ├── useGestion.ts
│   └── useDashboardStats.ts
├── pages/               # Páginas/vistas
│   ├── Login.tsx
│   ├── Dashboard.tsx    # Admin KPIs
│   ├── Sucursales.tsx   # Tabla de farmacias
│   ├── SucursalDetail.tsx  # Detalle con tabs
│   └── Admin.tsx        # Gestión de auditores
├── lib/
│   ├── supabase.ts      # Cliente Supabase
│   ├── api.ts           # Funciones de query a Supabase
│   └── utils.ts         # Formatters y helpers
├── types/
│   └── index.ts         # TypeScript interfaces
├── App.tsx              # Router setup
└── main.tsx
```

## Páginas

| Página | Rol | Descripción |
|--------|-----|-------------|
| **Login** | Público | Autenticación con Supabase |
| **Dashboard** | Admin | KPIs y gráficos de gestiones |
| **Sucursales** | Todos | Tabla de farmacias con búsqueda |
| **SucursalDetail** | Todos | Detalle: hallazgos, gestiones, stock |
| **Admin** | Admin | Crear/editar auditores |

## Hooks Disponibles

```typescript
// Autenticación
const { user, profile, role, loading } = useAuth();
await login(email, password);
await logout();

// Data fetching
const { sucursales, loading, error } = useSucursales();
const { reportes, loading, error } = useReportes({ sucursal_id: "123" });
const { gestiones, loading, error, updateStatus } = useGestion();
const { stats, loading, error } = useDashboardStats();
const { items, loading, error } = useControlStock(sucursal_id);
```

## Autenticación

- **Sistema**: Supabase Auth (email/password)
- **Roles**:
  - `admin` - acceso completo + admin panel
  - `auditor` - acceso limitado a sus datos (RLS automático)

Los usuarios se crean en Supabase > Authentication > Create user

## Build

```bash
npm run build          # Genera dist/
npm run preview        # Test la build localmente
```

## Deploy

### Netlify
```bash
npm run build
# Drag dist/ to Netlify
```

### Railway/Vercel
```bash
Build: npm run build
Output: dist
```

## Tips

- Tailwind está configurado, usa clases como `bg-blue-600`, `text-center`, etc.
- RLS filtra automáticamente datos por rol desde Supabase
- Los hooks usan Supabase SDK, no FastAPI endpoints
- AppLayout proporciona header/nav reutilizable

## Troubleshooting

| Problema | Solución |
|----------|----------|
| `.env.local` falta | Copiar `.env.example` y llenar valores |
| Login falla | Verificar usuario en Supabase > Authentication |
| Datos no cargan | Esperar 5 min para sync, o revisar logs del backend |
| Auditor ve datos ajenos | RLS no activado - ejecutar SQL desde `supabase_setup.sql` |
