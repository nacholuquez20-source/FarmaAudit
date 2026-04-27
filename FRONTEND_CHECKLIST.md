# Frontend Setup & QA Checklist

## Pre-Setup

- [ ] Node.js 18+ installed (`node --version`)
- [ ] npm installed (`npm --version`)

## Installation

- [ ] Clone repository
- [ ] `cd frontend && npm install` completed successfully
- [ ] No warnings in npm install output (or only optional warnings)

## Environment Setup

- [ ] `.env.local` file created in `frontend/` directory
- [ ] `VITE_SUPABASE_URL` set to correct Supabase URL
- [ ] `VITE_SUPABASE_ANON_KEY` populated with anon key from Supabase

## Backend Dependencies

- [ ] Supabase project created and tables initialized (`supabase_setup.sql` executed)
- [ ] At least one user created in Supabase Authentication
- [ ] User has a profile with `role = 'admin'` or `role = 'auditor'`
- [ ] Backend sync job running (`python main.py` on backend)
- [ ] Data synchronized from Google Sheets to Supabase (check logs for "Full sync completed")

## Dev Server

- [ ] `npm run dev` runs without errors
- [ ] Server listens on http://localhost:5173
- [ ] Page loads without console errors

## Authentication Flow

- [ ] Login page displays correctly
- [ ] Can log in with valid Supabase credentials
- [ ] Invalid credentials show error message
- [ ] Successful login redirects to /dashboard (admin) or /sucursales (auditor)
- [ ] Logout button works and redirects to /login
- [ ] User email displayed in header

## Dashboard Page (Admin)

- [ ] Loads without errors
- [ ] 4 KPI cards display correctly:
  - [ ] Total Reportes
  - [ ] Gestiones Abiertas
  - [ ] Gestiones Vencidas
  - [ ] Tasa Cierre %
- [ ] Pie chart displays gestion states
- [ ] Bar chart displays severity distribution
- [ ] Summary cards show correct numbers
- [ ] Navigation links work (to Sucursales, Admin)

## Sucursales Page

- [ ] Loads and displays all pharmacies in table
- [ ] Search filter works for nombre, zona, responsable
- [ ] Click on row navigates to detail page
- [ ] Navigation back from detail works
- [ ] Auditors see only their own (if RLS configured)

## SucursalDetail Page

- [ ] Sucursal info displays correctly (dirección, zona, responsable, tel)
- [ ] Reportes tab:
  - [ ] Shows all reports for this pharmacy
  - [ ] Severity badges color-coded correctly
  - [ ] Dates formatted properly
- [ ] Gestiones tab:
  - [ ] Shows all gestions for this pharmacy
  - [ ] Status states display correctly
- [ ] Stock tab:
  - [ ] Shows stock items
  - [ ] Alerts highlighted for differences

## Admin Page (Admin Only)

- [ ] Page loads (non-admin redirected to /sucursales)
- [ ] Auditores table displays all auditors
- [ ] "Agregar Auditor" button works
- [ ] Form fields validate (required fields)
- [ ] New auditor created and appears in table
- [ ] Active/Inactive toggle works
- [ ] Inactive auditors display red badge

## RLS & Security

- [ ] Admin can see all data
- [ ] Auditor can only see:
  - [ ] Their own reportes (filtered by telefono)
  - [ ] Their own control_stock
- [ ] Auditor cannot see Admin panel

## Build & Production

- [ ] `npm run build` succeeds
- [ ] `dist/` folder created with files
- [ ] `npm run preview` shows static build preview
- [ ] Build size is reasonable (< 500KB gzipped expected)

## Performance

- [ ] Page loads complete in < 2 seconds
- [ ] Smooth navigation between pages
- [ ] No memory leaks (check DevTools > Performance)
- [ ] Network requests to Supabase < 200ms (check DevTools > Network)

## Error Handling

- [ ] Network error shown if Supabase unreachable
- [ ] Form validation shows errors
- [ ] Toast/alert for failed operations
- [ ] Graceful fallback if data missing

## Responsive Design

- [ ] Works on desktop (1920px, 1366px)
- [ ] Works on tablet (768px)
- [ ] Works on mobile (375px)
- [ ] Buttons/links clickable on mobile
- [ ] No horizontal scroll on mobile

## Accessibility

- [ ] Page titles accessible in browser title
- [ ] Form labels associated with inputs
- [ ] Color not only indicator of status (text + color)
- [ ] Keyboard navigation works (Tab, Enter)

## Browser Compatibility

- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

## Deployment

### Netlify
- [ ] `npm run build` succeeds
- [ ] Drag `dist/` to Netlify
- [ ] Site deploys successfully
- [ ] Environment variables set in Netlify dashboard
- [ ] Custom domain configured (optional)

### Railway/Vercel
- [ ] Connected to GitHub repository
- [ ] Build command set to `npm run build`
- [ ] Output directory set to `dist`
- [ ] Environment variables configured
- [ ] Deployment succeeds
- [ ] Site accessible at deployment URL

## Known Issues & Workarounds

- [ ] (Document any known issues found during testing)

## Sign-off

- Tested by: ________________
- Date: ________________
- Status: ☐ PASS ☐ FAIL

### Notes:
```
(Any additional notes or issues found)
```
