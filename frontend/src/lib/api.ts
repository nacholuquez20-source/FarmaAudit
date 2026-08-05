import { supabase } from './supabase';
import type {
  Sucursal,
  SucursalDashboard,
  SucursalUpdate,
  Reporte,
  Gestion,
  Auditor,
  DashboardStats,
  ZonaResumen,
  GestionState,
  GestionUpdate,
  DesvioEvento,
  CreateDesvioEventoInput,
  UserProfile,
  BranchAgg,
  DesvioOrigen,
  Notificacion,
  NotificacionTipo,
  DesvioBorrador,
  CreatePanelUserInput,
  UpdatePanelUserInput,
  GestionRevisionAccion,
  Marca,
  Campania,
  CampaniaAccion,
  CampaniaAccionTipo,
  CampaniaTarea,
  CampaniaEvento,
  CampaniaEventoTipo,
  SolicitudInsumo,
  SolicitudInsumoProveedor,
  SolicitudInsumoTipo,
  CampaniaResultado,
} from '../types';

const VALID_STORAGE_BUCKETS = ['auditoria-respuestas', 'desvio-evidencias'] as const;
type ValidBucket = typeof VALID_STORAGE_BUCKETS[number];

function isValidBucket(bucket: unknown): bucket is ValidBucket {
  return typeof bucket === 'string' && VALID_STORAGE_BUCKETS.includes(bucket as ValidBucket);
}

function handleApiError(error: { message?: string }): string {
  if (import.meta.env.DEV) {
    return error.message || 'An error occurred';
  }
  return 'Error al obtener datos. Intente de nuevo.';
}

function getBotApiUrl(): string {
  const raw = String(import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');
  if (!raw) return '';
  const railwayHost = raw.match(/([a-z0-9-]+\.up\.railway\.app)/i)?.[1];
  if (railwayHost) return `https://${railwayHost}`;
  if (/^https?:\/\//i.test(raw)) return raw;
  return `https://${raw}`;
}

export async function getSucursales(): Promise<Sucursal[]> {
  const { data, error } = await supabase
    .from('sucursales')
    .select('*')
    .order('nombre');
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

// Centro de Operaciones: una sola query a la vista precalculada.
export async function getSucursalesDashboard(): Promise<SucursalDashboard[]> {
  const { data, error } = await supabase
    .from('sucursales_dashboard')
    .select('*')
    .order('nombre');
  if (error) throw new Error(handleApiError(error));
  return (data as SucursalDashboard[]) || [];
}

export async function getSucursal(id: string): Promise<Sucursal> {
  const { data, error } = await supabase
    .from('sucursales')
    .select('*')
    .eq('id', id)
    .single();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function updateSucursal(id: string, patch: SucursalUpdate): Promise<Sucursal> {
  const { data, error } = await supabase
    .from('sucursales')
    .update(patch)
    .eq('id', id)
    .select('*')
    .single();

  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function getReporte(id: string): Promise<Reporte | null> {
  const { data, error } = await supabase
    .from('reportes')
    .select('*')
    .eq('id', id)
    .maybeSingle();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function getReportes(params?: { sucursal_id?: string; auditor?: string }): Promise<Reporte[]> {
  let query = supabase
    .from('reportes')
    .select('*');

  if (params?.sucursal_id) {
    query = query.eq('id_sucursal', params.sucursal_id);
  }
  if (params?.auditor) {
    query = query.eq('auditor', params.auditor);
  }

  const { data, error } = await query.order('fecha', { ascending: false });
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function getGestion(params?: { sucursal_id?: string; estado?: string }): Promise<Gestion[]> {
  let query = supabase
    .from('gestion')
    .select('*');

  if (params?.sucursal_id) {
    query = query.eq('id_sucursal', params.sucursal_id);
  }
  if (params?.estado) {
    query = query.eq('estado', params.estado);
  }

  const { data, error } = await query.order('plazo_fecha');
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function getGestionById(id: string): Promise<Gestion | null> {
  const { data, error } = await supabase
    .from('gestion')
    .select('*')
    .eq('id_gestion', id)
    .maybeSingle();
  if (error) throw new Error(handleApiError(error));
  return data;
}

function isMissingTableError(error: { code?: string; message?: string }, tableName?: string): boolean {
  const message = error.message?.toLowerCase() || '';
  return (
    error.code === '42P01'
    || error.code === 'PGRST205'
    || (tableName ? message.includes(tableName.toLowerCase()) : false)
  );
}

function isMissingOptionalTableError(error: { code?: string; message?: string }): boolean {
  return isMissingTableError(error, 'desvio_eventos');
}

export async function getDesvioEventos(idGestion: string): Promise<DesvioEvento[]> {
  const { data, error } = await supabase
    .from('desvio_eventos')
    .select('*')
    .eq('id_gestion', idGestion)
    .order('created_at', { ascending: true });

  if (error) {
    if (isMissingOptionalTableError(error)) return [];
    throw new Error(handleApiError(error));
  }

  return data || [];
}

export async function createDesvioEvento(input: CreateDesvioEventoInput): Promise<DesvioEvento> {
  const { data, error } = await supabase
    .from('desvio_eventos')
    .insert([input])
    .select()
    .single();

  if (error) {
    if (isMissingOptionalTableError(error)) {
      throw new Error('La tabla desvio_eventos no existe. Ejecuta frontend/docs/sql/etapa-2.sql en Supabase.');
    }
    throw new Error(handleApiError(error));
  }

  return data;
}

export async function updateGestion(id: string, estado: GestionState, cerrado_por?: string): Promise<Gestion> {
  const updateData: GestionUpdate = { estado };
  if (cerrado_por) {
    updateData.cerrado_por = cerrado_por;
    if (estado === 'Cerrada') {
      updateData.fecha_cierre = new Date().toISOString().split('T')[0];
    }
  }

  const { data, error } = await supabase
    .from('gestion')
    .update(updateData)
    .eq('id_gestion', id)
    .select()
    .single();

  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function revisarGestion(input: {
  idGestion: string;
  accion: GestionRevisionAccion;
  motivo?: string;
  plazoDias?: number;
}): Promise<Gestion> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }

  const response = await fetch(`${apiUrl}/api/gestion/${encodeURIComponent(input.idGestion)}/revision`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({
      accion: input.accion,
      motivo: input.motivo,
      plazo_dias: input.plazoDias,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'No se pudo procesar la revision del desvio.');
  }

  return response.json();
}

export async function notificarEncargado(input: {
  idGestion: string;
  telefonoEncargado: string;
  descripcionDesvio: string;
  sucursal?: string;
}): Promise<void> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }

  const response = await fetch(`${apiUrl}/api/send-encargado-notification`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id_gestion: input.idGestion,
      telefono_encargado: input.telefonoEncargado,
      descripcion_desvio: input.descripcionDesvio,
      sucursal: input.sucursal,
    }),
  });

  if (!response.ok) {
    throw new Error('No se pudo notificar al encargado por WhatsApp.');
  }
}

export async function uploadEvidencia(
  idGestion: string,
  file: File,
  origen: DesvioOrigen,
): Promise<{ path: string; signedUrl: string }> {
  const fallbackExt = file.type === 'application/pdf' ? 'pdf' : 'jpg';
  const ext = file.name.split('.').pop()?.toLowerCase() || fallbackExt;
  const path = `gestion/${idGestion}/${origen}-${crypto.randomUUID()}.${ext}`;

  const { error } = await supabase.storage
    .from('desvio-evidencias')
    .upload(path, file, { contentType: file.type, upsert: false });

  if (error) throw new Error(handleApiError(error));

  const { data: signed, error: signedError } = await supabase.storage
    .from('desvio-evidencias')
    .createSignedUrl(path, 60 * 60 * 24);

  if (signedError) throw new Error(handleApiError(signedError));
  return { path, signedUrl: signed?.signedUrl ?? '' };
}

function getEvidenceBucket(path: string): ValidBucket {
  return path.startsWith('auditoria/') ? 'auditoria-respuestas' : 'desvio-evidencias';
}

export async function getSignedUrl(path: string, bucket: string = getEvidenceBucket(path)): Promise<string> {
  if (!isValidBucket(bucket)) {
    throw new Error(`Invalid storage bucket: ${bucket}. Allowed: ${VALID_STORAGE_BUCKETS.join(', ')}`);
  }
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, 60 * 60 * 24);

  if (error) throw new Error(handleApiError(error));
  return data?.signedUrl ?? '';
}

export function parseStorageUrl(value?: string | null): { bucket: ValidBucket; path: string } | null {
  if (!value) return null;
  if (value.startsWith('storage://')) {
    const withoutProtocol = value.replace('storage://', '');
    const [bucket, ...pathParts] = withoutProtocol.split('/');
    const path = pathParts.join('/');
    if (!bucket || !path || !isValidBucket(bucket)) return null;
    return { bucket, path };
  }
  if (value.startsWith('auditoria/')) {
    return { bucket: 'auditoria-respuestas', path: value };
  }
  if (value.startsWith('gestion/')) {
    return { bucket: 'desvio-evidencias', path: value };
  }
  return null;
}

export async function resolveEvidenceUrl(value?: string | null): Promise<string> {
  if (!value) return '';
  const storage = parseStorageUrl(value);
  if (!storage) return value;
  return getSignedUrl(storage.path, storage.bucket);
}

export async function resolveEvidenceThumbUrl(evidencia?: { thumb_path?: string; path?: string; bucket?: string; url?: string }): Promise<string> {
  if (!evidencia) return '';
  if (evidencia.thumb_path) {
    try {
      const bucket = evidencia.bucket && isValidBucket(evidencia.bucket)
        ? evidencia.bucket
        : getEvidenceBucket(evidencia.thumb_path);
      return getSignedUrl(evidencia.thumb_path, bucket);
    } catch {
      return '';
    }
  }
  if (evidencia.path) {
    return resolveEvidenceUrl(evidencia.path);
  }
  return evidencia.url || '';
}

export async function enviarMensajeInterno(input: {
  idGestion: string;
  comentario: string;
  origen: DesvioOrigen;
  actorId: string;
  actorNombre: string;
}): Promise<DesvioEvento> {
  const apiUrl = getBotApiUrl();
  if (apiUrl) {
    const response = await fetch(`${apiUrl}/api/gestion/${encodeURIComponent(input.idGestion)}/mensajes`, {
      method: 'POST',
      headers: await getAuthHeaders(),
      body: JSON.stringify({
        comentario: input.comentario,
        origen: input.origen,
        actor_id: input.actorId || undefined,
        actor_nombre: input.actorNombre || undefined,
      }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail || 'No se pudo enviar el comentario.');
    }

    return response.json();
  }

  return createDesvioEvento({
    id_gestion: input.idGestion,
    tipo: 'mensaje',
    comentario: input.comentario,
    actor_id: input.actorId,
    actor_nombre: input.actorNombre,
    metadata: {
      origen: input.origen,
      leido_por_auditor: input.origen === 'auditor',
      leido_por_sucursal: input.origen === 'sucursal',
    },
  });
}

export async function getNotificaciones(): Promise<Notificacion[]> {
  const { data, error } = await supabase
    .from('desvio_notificaciones')
    .select('*')
    .eq('leida', false)
    .order('created_at', { ascending: false });

  if (error) {
    if (error.code === '42P01' || error.code === 'PGRST205') return [];
    throw new Error(handleApiError(error));
  }

  return (data ?? []) as Notificacion[];
}

export async function marcarNotificacionLeida(id: string): Promise<void> {
  const { error } = await supabase
    .from('desvio_notificaciones')
    .update({ leida: true })
    .eq('id', id);

  if (error) throw new Error(handleApiError(error));
}

export async function getDesviosBorrador(): Promise<DesvioBorrador[]> {
  const { data, error } = await supabase
    .from('desvios_borrador')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) {
    if (isMissingTableError(error, 'desvios_borrador')) return [];
    throw new Error(handleApiError(error));
  }

  return (data ?? []) as DesvioBorrador[];
}

async function getAuthHeaders(): Promise<HeadersInit> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) {
    throw new Error('Sesion no disponible. Volve a iniciar sesion.');
  }
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

export async function approveDesvioBorrador(id: string): Promise<{ id_gestion: string; id_reporte: string }> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }

  const url = `${apiUrl}/api/desvios-borrador/${id}/approve`;
  let response = await fetch(url, {
    method: 'POST',
    headers: await getAuthHeaders(),
  });
  if (response.status === 405) {
    response = await fetch(url, {
      method: 'GET',
      headers: await getAuthHeaders(),
    });
  }

  if (!response.ok) {
    throw new Error('No se pudo aprobar el borrador.');
  }

  return response.json();
}

export async function discardDesvioBorrador(id: string, reason = ''): Promise<void> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }

  const url = `${apiUrl}/api/desvios-borrador/${id}/discard`;
  let response = await fetch(url, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({ reason }),
  });
  if (response.status === 405) {
    response = await fetch(url, {
      method: 'GET',
      headers: await getAuthHeaders(),
    });
  }

  if (!response.ok) {
    throw new Error('No se pudo descartar el borrador.');
  }
}

async function getNotificationRecipients(idGestion: string, origen: DesvioOrigen): Promise<string[]> {
  const gestion = await getGestionById(idGestion);
  if (!gestion) return [];

  const { data: authData } = await supabase.auth.getUser();
  const currentUserId = authData.user?.id ?? null;

  if (origen === 'sucursal') {
    const { data, error } = await supabase
      .from('profiles')
      .select('id')
      .in('role', ['admin', 'auditor']);

    if (error) return [];
    return (data ?? [])
      .map((row) => String(row.id))
      .filter((id) => id !== currentUserId);
  }

  try {
    const { data, error } = await supabase
      .from('profiles')
      .select('id')
      .eq('role', 'sucursal')
      .eq('id_sucursal', gestion.id_sucursal);

    if (error) return [];
    return (data ?? [])
      .map((row) => String(row.id))
      .filter((id) => id !== currentUserId);
  } catch {
    return [];
  }
}

export async function crearNotificacionesDesvio(input: {
  idGestion: string;
  origen: DesvioOrigen;
  tipo: NotificacionTipo;
}): Promise<void> {
  const recipients = await getNotificationRecipients(input.idGestion, input.origen);
  if (recipients.length === 0) return;

  const { error } = await supabase
    .from('desvio_notificaciones')
    .insert(
      recipients.map((userId) => ({
        id_gestion: input.idGestion,
        user_id: userId,
        tipo: input.tipo,
      })),
    );

  if (error) {
    if (error.code === '42P01' || error.code === 'PGRST205') return;
    throw new Error(handleApiError(error));
  }
}

export async function getAuditores(): Promise<Auditor[]> {
  const { data, error } = await supabase
    .from('auditores')
    .select('*')
    .order('nombre');
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function createAuditor(auditor: Auditor): Promise<Auditor> {
  const { data, error } = await supabase
    .from('auditores')
    .insert([auditor])
    .select()
    .single();

  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function updateAuditor(telefono: string, data: Partial<Auditor>): Promise<Auditor> {
  const { data: result, error } = await supabase
    .from('auditores')
    .update(data)
    .eq('telefono', telefono)
    .select()
    .single();

  if (error) throw new Error(handleApiError(error));
  return result;
}

export async function getMarcas(): Promise<Marca[]> {
  const { data, error } = await supabase
    .from('marcas')
    .select('*')
    .order('nombre');
  if (error) {
    if (isMissingTableError(error, 'marcas')) return [];
    throw new Error(handleApiError(error));
  }
  return data || [];
}

export async function createMarca(nombre: string): Promise<Marca> {
  const { data, error } = await supabase
    .from('marcas')
    .insert([{ nombre }])
    .select()
    .single();

  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function updateMarca(id: string, patch: Partial<Pick<Marca, 'nombre' | 'activo'>>): Promise<Marca> {
  const { data, error } = await supabase
    .from('marcas')
    .update(patch)
    .eq('id', id)
    .select()
    .single();

  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function listPanelProfiles(): Promise<UserProfile[]> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) throw new Error('Falta configurar VITE_API_URL con la URL del bot.');

  const response = await fetch(`${apiUrl}/api/admin/panel-users`, {
    method: 'GET',
    headers: await getAuthHeaders(),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'No se pudo cargar usuarios del panel.');
  }
  return response.json();
}

export async function createPanelUser(input: CreatePanelUserInput): Promise<UserProfile> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) throw new Error('Falta configurar VITE_API_URL con la URL del bot.');

  const response = await fetch(`${apiUrl}/api/admin/panel-users`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'No se pudo crear el usuario.');
  }
  return response.json();
}

export async function updatePanelProfile(
  id: string,
  patch: UpdatePanelUserInput,
): Promise<UserProfile> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) throw new Error('Falta configurar VITE_API_URL con la URL del bot.');

  const response = await fetch(`${apiUrl}/api/admin/panel-users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: await getAuthHeaders(),
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'No se pudo guardar el usuario.');
  }
  return response.json();
}

function getGestionDate(gestion: Gestion): string | null {
  return gestion.created_at || gestion.updated_at || gestion.plazo_fecha || null;
}

function getDateKey(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().split('T')[0];
}

function createLastDays(days: number): string[] {
  const result: string[] = [];
  const today = new Date();

  for (let index = days - 1; index >= 0; index -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - index);
    result.push(date.toISOString().split('T')[0]);
  }

  return result;
}

function isCriticoActivo(severidad: string | null | undefined, estado: string | null | undefined): boolean {
  if (severidad !== 'Alta') return false;
  return estado === 'Abierta' || estado === 'En_proceso' || estado === 'Vencida';
}

function computeBranchScore(row: {
  vencidos: number;
  criticos_activos: number;
  abiertos: number;
}): number {
  let score = 100;
  score -= row.vencidos * 15;
  score -= row.criticos_activos * 12;
  score -= Math.min(36, Math.max(0, row.abiertos - row.criticos_activos) * 3);
  return Math.max(0, Math.round(score));
}

function resolveSemaforo(row: {
  vencidos: number;
  criticos_activos: number;
  abiertos: number;
  altas: number;
}): 'verde' | 'amarillo' | 'rojo' {
  if (row.vencidos > 0 || row.criticos_activos > 0) return 'rojo';
  if (row.abiertos > 0 || row.altas > 0) return 'amarillo';
  return 'verde';
}

function getDemoData(): DashboardStats {
  return {
    total_reportes: 48,
    total_desvios: 12,
    gestiones_abiertas: 5,
    gestiones_vencidas: 2,
    gestiones_resueltas: 3,
    gestiones_cerradas: 2,
    tasa_cierre: 33,
    sucursales_sin_auditoria: 0,
    criticos_activos: 2,
    criticos_vencidos: 1,
    severidad: { alta: 3, media: 5, baja: 4 },
    sucursales_estado: [
      {
        id_sucursal: 'demo-1',
        sucursal: 'Sucursal Centro',
        zona: 'Centro',
        abiertos: 2,
        vencidos: 1,
        altas: 2,
        criticos_activos: 1,
        resueltos: 1,
        cerrados: 1,
        total: 5,
        puntaje: 76,
        semaforo: 'rojo',
      },
      {
        id_sucursal: 'demo-2',
        sucursal: 'Sucursal Norte',
        zona: 'Norte',
        abiertos: 2,
        vencidos: 1,
        altas: 1,
        criticos_activos: 1,
        resueltos: 1,
        cerrados: 0,
        total: 4,
        puntaje: 64,
        semaforo: 'rojo',
      },
      {
        id_sucursal: 'demo-3',
        sucursal: 'Sucursal Sur',
        zona: 'Sur',
        abiertos: 1,
        vencidos: 0,
        altas: 0,
        criticos_activos: 0,
        resueltos: 1,
        cerrados: 1,
        total: 3,
        puntaje: 88,
        semaforo: 'amarillo',
      },
    ],
    ranking_sucursales: [
      { id_sucursal: 'demo-1', sucursal: 'Sucursal Centro', abiertos: 2, vencidos: 1, altas: 2, criticos_activos: 1 },
      { id_sucursal: 'demo-2', sucursal: 'Sucursal Norte', abiertos: 2, vencidos: 1, altas: 1, criticos_activos: 1 },
    ],
    tendencia_ultimos_30_dias: Array.from({ length: 30 }, (_, i) => {
      const fecha = new Date();
      fecha.setDate(fecha.getDate() - (29 - i));
      return {
        fecha: fecha.toISOString().split('T')[0],
        total: Math.floor(Math.random() * 10) + 2,
        cerrados: Math.floor(Math.random() * 5) + 1,
      };
    }),
    por_zona: [
      { zona: 'Centro', sucursales: 1, total_desvios: 5, abiertos: 2, vencidos: 1, criticos_activos: 1, puntaje_promedio: 76 },
      { zona: 'Norte', sucursales: 1, total_desvios: 4, abiertos: 2, vencidos: 1, criticos_activos: 1, puntaje_promedio: 64 },
      { zona: 'Sur', sucursales: 1, total_desvios: 3, abiertos: 1, vencidos: 0, criticos_activos: 0, puntaje_promedio: 88 },
    ],
    isDemoData: true,
  };
}

export async function getDashboardStats(sucursalId?: string | null): Promise<DashboardStats> {
  try {
    let reportesQuery = supabase.from('reportes').select('*');
    let gestionQuery = supabase.from('gestion').select('*');
    if (sucursalId) {
      reportesQuery = reportesQuery.eq('id_sucursal', sucursalId);
      gestionQuery = gestionQuery.eq('id_sucursal', sucursalId);
    }

    const sucursalesQuery = sucursalId
      ? supabase.from('sucursales').select('id,nombre,zona').eq('id', sucursalId)
      : supabase.from('sucursales').select('id,nombre,zona').order('nombre');

    const [reportesRes, gestionRes, sucursalesRes] = await Promise.all([
      reportesQuery,
      gestionQuery,
      sucursalesQuery,
    ]);

    if (reportesRes.error) throw new Error(reportesRes.error.message);
    if (gestionRes.error) throw new Error(gestionRes.error.message);
    if (sucursalesRes.error) throw new Error(sucursalesRes.error.message);

    const reportes = reportesRes.data || [];
    const gestiones = gestionRes.data || [];
    const sucursalesRows = sucursalesRes.data || [];

    // Return demo data if empty
    if (reportes.length === 0 && gestiones.length === 0 && sucursalesRows.length === 0) {
      return getDemoData();
    }

    const zonaPorSucursal = new Map(sucursalesRows.map((s) => [s.id as string, (s.zona as string)?.trim() || 'Sin zona']));
    const nombrePorSucursal = new Map(sucursalesRows.map((s) => [s.id as string, String(s.nombre || '')]));

    const total_reportes = reportes.length;
    const total_desvios = gestiones.length;
    const gestiones_abiertas = gestiones.filter((g) => g.estado === 'Abierta' || g.estado === 'En_proceso').length;
    const gestiones_vencidas = gestiones.filter((g) => g.estado === 'Vencida').length;
    const gestiones_resueltas = gestiones.filter((g) => g.estado === 'Resuelta').length;
    const gestiones_cerradas = gestiones.filter((g) => g.estado === 'Cerrada').length;
    const tasa_cierre = gestiones.length > 0 ? Math.round((gestiones_cerradas / gestiones.length) * 100) : 0;

    const criticos_activos = gestiones.filter((g) => isCriticoActivo(g.severidad, g.estado)).length;
    const criticos_vencidos = gestiones.filter((g) => g.severidad === 'Alta' && g.estado === 'Vencida').length;

    const severidad = {
      alta: gestiones.filter((g) => g.severidad === 'Alta').length,
      media: gestiones.filter((g) => g.severidad === 'Media').length,
      baja: gestiones.filter((g) => g.severidad === 'Baja').length,
    };

    const sucursalesMap = new Map<string, BranchAgg>();

    gestiones.forEach((gestion) => {
      const key = gestion.id_sucursal || gestion.sucursal || 'sin-id';
      const idS = gestion.id_sucursal || key;
      const zona = (gestion.id_sucursal && zonaPorSucursal.get(gestion.id_sucursal)) || 'Sin zona';
      const nombreMaestro = gestion.id_sucursal ? nombrePorSucursal.get(gestion.id_sucursal) : undefined;
      const current = sucursalesMap.get(key) || {
        id_sucursal: idS,
        sucursal: nombreMaestro || gestion.sucursal || 'Sin sucursal',
        zona,
        abiertos: 0,
        vencidos: 0,
        altas: 0,
        criticos_activos: 0,
        resueltos: 0,
        cerrados: 0,
        total: 0,
      };

      current.total += 1;
      if (gestion.estado === 'Abierta' || gestion.estado === 'En_proceso') current.abiertos += 1;
      if (gestion.estado === 'Vencida') current.vencidos += 1;
      if (gestion.estado === 'Resuelta') current.resueltos += 1;
      if (gestion.estado === 'Cerrada') current.cerrados += 1;
      if (gestion.severidad === 'Alta') current.altas += 1;
      if (isCriticoActivo(gestion.severidad, gestion.estado)) current.criticos_activos += 1;
      if (gestion.id_sucursal) {
        current.zona = zonaPorSucursal.get(gestion.id_sucursal) || 'Sin zona';
        current.sucursal = nombreMaestro || gestion.sucursal || current.sucursal;
      }
      sucursalesMap.set(key, current);
    });

    const sucursales_estado = Array.from(sucursalesMap.values())
      .map((sucursal) => {
        const puntaje = computeBranchScore(sucursal);
        return {
          ...sucursal,
          puntaje,
          semaforo: resolveSemaforo(sucursal),
        };
      })
      .sort(
        (a, b) =>
          b.vencidos - a.vencidos ||
          b.criticos_activos - a.criticos_activos ||
          b.altas - a.altas ||
          b.abiertos - a.abiertos ||
          a.sucursal.localeCompare(b.sucursal),
      );

    const ranking_sucursales = sucursales_estado
      .filter((sucursal) => sucursal.abiertos > 0 || sucursal.vencidos > 0 || sucursal.criticos_activos > 0)
      .map((sucursal) => ({
        id_sucursal: sucursal.id_sucursal,
        sucursal: sucursal.sucursal,
        abiertos: sucursal.abiertos,
        vencidos: sucursal.vencidos,
        altas: sucursal.altas,
        criticos_activos: sucursal.criticos_activos,
      }))
      .slice(0, 10);

    const porZonaMap = new Map<
      string,
      { zona: string; sucursales: Set<string>; totales: BranchAgg }
    >();

    const ingestZonaBranch = (zonaRaw: string, branchId: string, fill: BranchAgg | null) => {
      const zona = zonaRaw?.trim() || 'Sin zona';
      let bucket = porZonaMap.get(zona);
      if (!bucket) {
        bucket = { zona, sucursales: new Set(), totales: {
          id_sucursal: '',
          sucursal: '',
          zona,
          abiertos: 0,
          vencidos: 0,
          altas: 0,
          criticos_activos: 0,
          resueltos: 0,
          cerrados: 0,
          total: 0,
        } };
        porZonaMap.set(zona, bucket);
      }
      bucket.sucursales.add(branchId);
      if (fill) {
        bucket.totales.abiertos += fill.abiertos;
        bucket.totales.vencidos += fill.vencidos;
        bucket.totales.altas += fill.altas;
        bucket.totales.criticos_activos += fill.criticos_activos;
        bucket.totales.resueltos += fill.resueltos;
        bucket.totales.cerrados += fill.cerrados;
        bucket.totales.total += fill.total;
      }
    };

    sucursales_estado.forEach((row) => {
      ingestZonaBranch(row.zona, row.id_sucursal || row.sucursal, {
        id_sucursal: row.id_sucursal,
        sucursal: row.sucursal,
        zona: row.zona,
        abiertos: row.abiertos,
        vencidos: row.vencidos,
        altas: row.altas,
        criticos_activos: row.criticos_activos,
        resueltos: row.resueltos,
        cerrados: row.cerrados,
        total: row.total,
      });
    });

    if (!sucursalId) {
      sucursalesRows.forEach((s) => {
        const id = s.id as string;
        const zona = (s.zona as string)?.trim() || 'Sin zona';
        if (!sucursalesMap.has(id)) ingestZonaBranch(zona, id, null);
      });
    }

    const por_zona: ZonaResumen[] = Array.from(porZonaMap.values())
      .map((bucket) => {
        const branchesInZone = sucursalesRows.filter((s) => ((s.zona as string)?.trim() || 'Sin zona') === bucket.zona);
        const scores = branchesInZone.map((s) => {
          const row = sucursales_estado.find((item) => item.id_sucursal === s.id);
          return row ? row.puntaje : 100;
        });
        const puntaje_promedio = scores.length > 0
          ? Math.round(scores.reduce((acc, val) => acc + val, 0) / scores.length)
          : 100;
        return {
          zona: bucket.zona,
          sucursales: bucket.sucursales.size || branchesInZone.length,
          total_desvios: bucket.totales.total,
          abiertos: bucket.totales.abiertos,
          vencidos: bucket.totales.vencidos,
          criticos_activos: bucket.totales.criticos_activos,
          puntaje_promedio,
        };
      })
      .sort((a, b) => b.criticos_activos - a.criticos_activos || b.vencidos - a.vencidos || a.zona.localeCompare(b.zona));

    const last30Days = createLastDays(30);
    const trendMap = new Map(last30Days.map((fecha) => [fecha, { fecha, total: 0, cerrados: 0 }]));

    gestiones.forEach((gestion) => {
      const dateValue = getGestionDate(gestion);
      if (!dateValue) return;
      const dayKey = getDateKey(dateValue);
      if (!dayKey || !trendMap.has(dayKey)) return;

      const current = trendMap.get(dayKey);
      if (!current) return;
      current.total += 1;
      if (gestion.estado === 'Cerrada') current.cerrados += 1;
    });

    const tendencia_ultimos_30_dias = Array.from(trendMap.values());
    const sucursalesConReportes = new Set(reportes.map((reporte) => reporte.id_sucursal).filter(Boolean));
    const sucursalesConGestiones = new Set(gestiones.map((gestion) => gestion.id_sucursal).filter(Boolean));
    const sucursales_sin_auditoria = Array.from(sucursalesConReportes).filter((id) => !sucursalesConGestiones.has(id)).length;

    return {
      total_reportes,
      total_desvios,
      gestiones_abiertas,
      gestiones_vencidas,
      gestiones_resueltas,
      gestiones_cerradas,
      tasa_cierre,
      sucursales_sin_auditoria,
      criticos_activos,
      criticos_vencidos,
      severidad,
      sucursales_estado,
      ranking_sucursales,
      tendencia_ultimos_30_dias,
      por_zona,
    };
  } catch (error) {
    throw new Error('Failed to fetch dashboard stats', { cause: error });
  }
}

export async function submitPerfumeriaAudit(payload: {
  id_sesion: string;
  sucursal_id: string;
  sucursal_nombre: string;
  auditor_nombre: string;
  auditor_telefono: string;
  bloques_scores: Array<{ id: string; nombre: string; puntuacion: number }>;
  desvios: Array<{ id: string; bloque: string; descripcion: string; foto_url?: string | null }>;
}): Promise<{ status: string; deviations_created: number }> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }

  const response = await fetch(`${apiUrl}/api/auditorias-completadas/perfumeria`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(errorData.detail || 'No se pudo guardar la auditoría');
  }

  return response.json();
}

// ============ Modulo Campanias (ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 2) ============

export async function getCampanias(): Promise<Campania[]> {
  const { data, error } = await supabase
    .from('campanias')
    .select('*, marcas(nombre)')
    .order('created_at', { ascending: false });
  if (error) {
    if (isMissingTableError(error, 'campanias')) return [];
    throw new Error(handleApiError(error));
  }
  return (data ?? []) as Campania[];
}

export async function getCampaniaById(id: string): Promise<Campania | null> {
  const { data, error } = await supabase
    .from('campanias')
    .select('*, marcas(nombre)')
    .eq('id', id)
    .maybeSingle();
  if (error) throw new Error(handleApiError(error));
  return data as Campania | null;
}

export async function createCampania(input: {
  nombre: string;
  marca_id: string;
  acuerdo_desde?: string | null;
  acuerdo_hasta?: string | null;
  contraprestacion?: string | null;
  creado_por?: string | null;
}): Promise<Campania> {
  const { data, error } = await supabase
    .from('campanias')
    .insert([input])
    .select()
    .single();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function createCampaniaAcciones(
  campaniaId: string,
  acciones: { tipo: CampaniaAccionTipo; descripcion?: string; requiere_foto?: boolean; verificable_por_foto?: boolean }[],
): Promise<CampaniaAccion[]> {
  const rows = acciones.map((accion) => ({
    campania_id: campaniaId,
    tipo: accion.tipo,
    descripcion: accion.descripcion || null,
    requiere_foto: accion.requiere_foto ?? true,
    // descuento_caja depende del sistema de caja, no de una foto del encargado (ver arquitectura).
    verificable_por_foto: accion.verificable_por_foto ?? accion.tipo !== 'descuento_caja',
  }));
  const { data, error } = await supabase.from('campania_acciones').insert(rows).select();
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function getCampaniaAcciones(campaniaId: string): Promise<CampaniaAccion[]> {
  const { data, error } = await supabase
    .from('campania_acciones')
    .select('*')
    .eq('campania_id', campaniaId)
    .order('created_at');
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function activarCampania(campaniaId: string, sucursalIds: string[]): Promise<{ status: string; tareas_creadas: number }> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }
  const response = await fetch(`${apiUrl}/api/campanias/${encodeURIComponent(campaniaId)}/activar`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify({ sucursal_ids: sucursalIds }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'No se pudo activar la campania.');
  }
  return response.json();
}

export async function getCampaniaTareas(campaniaId: string): Promise<CampaniaTarea[]> {
  const { data, error } = await supabase
    .from('campania_tareas')
    .select('*, campania_acciones(*), sucursales(nombre)')
    .eq('campania_id', campaniaId)
    .order('created_at');
  if (error) throw new Error(handleApiError(error));
  return (data ?? []) as CampaniaTarea[];
}

export async function getMisCampaniaTareas(idSucursal: string): Promise<CampaniaTarea[]> {
  const { data, error } = await supabase
    .from('campania_tareas')
    .select('*, campania_acciones(*), campanias!inner(nombre, estado, marcas(nombre))')
    .eq('id_sucursal', idSucursal)
    .in('campanias.estado', ['Activa', 'En_seguimiento'])
    .order('created_at');
  if (error) throw new Error(handleApiError(error));
  return (data ?? []) as CampaniaTarea[];
}

export async function updateCampaniaTarea(tareaId: string, patch: Partial<Pick<CampaniaTarea, 'estado' | 'vista_at' | 'evidencia_path'>>): Promise<CampaniaTarea> {
  const { data, error } = await supabase
    .from('campania_tareas')
    .update(patch)
    .eq('id', tareaId)
    .select()
    .single();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function getCampaniaEventos(tareaId: string): Promise<CampaniaEvento[]> {
  const { data, error } = await supabase
    .from('campania_eventos')
    .select('*')
    .eq('tarea_id', tareaId)
    .order('created_at');
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function createCampaniaEvento(input: {
  tarea_id: string;
  tipo: CampaniaEventoTipo;
  comentario?: string;
  actor_id?: string | null;
  actor_nombre?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<CampaniaEvento> {
  const { data, error } = await supabase.from('campania_eventos').insert([input]).select().single();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function createSolicitudInsumo(input: {
  tarea_id: string;
  tipo_insumo: SolicitudInsumoTipo;
  detalle?: string;
  cantidad?: string;
  proveedor: SolicitudInsumoProveedor;
  contacto_trade?: string;
}): Promise<SolicitudInsumo> {
  const { data, error } = await supabase
    .from('solicitudes_insumo')
    .insert([{
      ...input,
      // El material del laboratorio/APM no lo controla la cadena: no hay
      // "aprobacion" interna, se escala directo (ver arquitectura, Modulo 2).
      estado: input.proveedor === 'laboratorio_apm' ? 'Escalado_a_labo' : 'Solicitado',
    }])
    .select()
    .single();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function getSolicitudesInsumoPorTareas(tareaIds: string[]): Promise<SolicitudInsumo[]> {
  if (tareaIds.length === 0) return [];
  const { data, error } = await supabase
    .from('solicitudes_insumo')
    .select('*')
    .in('tarea_id', tareaIds)
    .order('created_at', { ascending: false });
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function resolverSolicitudInsumo(
  insumo: SolicitudInsumo,
  nuevoEstado: SolicitudInsumo['estado'],
  aprobadoPor?: string | null,
): Promise<SolicitudInsumo> {
  const { data, error } = await supabase
    .from('solicitudes_insumo')
    .update({ estado: nuevoEstado, aprobado_por: aprobadoPor || null })
    .eq('id', insumo.id)
    .select()
    .single();
  if (error) throw new Error(handleApiError(error));

  if (nuevoEstado === 'Recibido') {
    // El insumo llego: la tarea que estaba bloqueada vuelve a quedar disponible.
    await updateCampaniaTarea(insumo.tarea_id, { estado: 'Pendiente' });
  }

  return data;
}

export async function createCampaniaResultado(input: {
  campania_id: string;
  id_sucursal: string;
  venta_periodo_campania?: number | null;
  venta_periodo_base?: number | null;
  unidad: 'unidades' | 'pesos';
  cargado_por?: string | null;
}): Promise<CampaniaResultado> {
  const { data, error } = await supabase.from('campania_resultados').insert([input]).select().single();
  if (error) throw new Error(handleApiError(error));
  return data;
}

export async function getCampaniaResultados(campaniaId: string): Promise<CampaniaResultado[]> {
  const { data, error } = await supabase
    .from('campania_resultados')
    .select('*')
    .eq('campania_id', campaniaId)
    .order('created_at', { ascending: false });
  if (error) throw new Error(handleApiError(error));
  return data || [];
}

export async function exportControlesPdf(filters: {
  sucursalId?: string;
  fechaDesde?: string;
  fechaHasta?: string;
}): Promise<Blob> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) {
    throw new Error('Falta configurar VITE_API_URL con la URL del bot.');
  }

  const params = new URLSearchParams();
  if (filters.sucursalId) params.set('sucursal_id', filters.sucursalId);
  if (filters.fechaDesde) params.set('fecha_desde', filters.fechaDesde);
  if (filters.fechaHasta) params.set('fecha_hasta', `${filters.fechaHasta}T23:59:59`);

  const headers = await getAuthHeaders();
  const response = await fetch(`${apiUrl}/api/audit-fiches/export-pdf?${params.toString()}`, {
    headers,
  });

  if (!response.ok) {
    throw new Error('No se pudo generar el PDF de controles.');
  }

  return response.blob();
}

// ─── Multi-agent audit analysis ──────────────────────────────────────────────

export interface AgenteCampo {
  resumen_ejecutivo: string;
  bloques_criticos: string[];
  bloques_destacados: string[];
  calidad_evidencia: 'alta' | 'media' | 'baja';
  diagnostico_general: 'positivo' | 'regular' | 'critico';
}

export interface AgenteCalidad {
  tendencia_general: 'mejorando' | 'estable' | 'deteriorando';
  variacion_score_vs_anterior: number | null;
  desvios_reincidentes: string[];
  bloques_mejorando: string[];
  bloques_deteriorando: string[];
  nivel_riesgo_historico: 'bajo' | 'medio' | 'alto' | 'critico';
  recomendacion_frecuencia_auditoria: 'quincenal' | 'mensual' | 'bimestral';
}

export interface AgentePerfumeria {
  marcas_potencialmente_afectadas: string[];
  riesgo_acuerdo_comercial: 'bajo' | 'medio' | 'alto';
  desvios_criticos_perfumeria: string[];
  impacto_exhibicion: string;
  acciones_urgentes: string[];
  planograma_comprometido: boolean;
}

export interface AgenteNormativo {
  nivel_alerta_anmat: 'verde' | 'amarillo' | 'naranja' | 'rojo';
  desvios_con_riesgo_regulatorio: string[];
  areas_riesgo: string[];
  recomendacion_normativa: string;
  requiere_accion_inmediata: boolean;
  plazo_regularizacion_max_dias: number;
}

export interface AgenteNegocio {
  score_salud_negocio: number;
  riesgo_perdida_ventas: 'bajo' | 'medio' | 'alto' | 'critico';
  desvios_mayor_impacto_economico: string[];
  prioridades: { desvio: string; prioridad: number; impacto: string; plazo_dias: number }[];
  inversion_requerida: 'baja' | 'media' | 'alta';
  retorno_esperado: string;
}

export interface Sintesis {
  diagnostico_integral: string;
  nivel_urgencia: 'normal' | 'urgente' | 'critico';
  score_riesgo_global: number;
  top_3_acciones_inmediatas: string[];
  proxima_auditoria_en_dias: number;
  mensaje_para_encargado: string;
}

export interface AnalisisAuditoria {
  ficha_id: string;
  sucursal_id: string;
  fecha_auditoria: string;
  agentes: {
    campo: AgenteCampo;
    calidad: AgenteCalidad;
    perfumeria: AgentePerfumeria;
    normativo: AgenteNormativo;
    negocio: AgenteNegocio;
  };
  sintesis: Sintesis;
  generado_en: string;
}

export async function analisisAuditoria(fichaId: string): Promise<AnalisisAuditoria> {
  const apiUrl = getBotApiUrl();
  if (!apiUrl) throw new Error('Falta configurar VITE_API_URL con la URL del bot.');

  const response = await fetch(`${apiUrl}/api/analisis/ficha/${encodeURIComponent(fichaId)}`, {
    method: 'POST',
    headers: await getAuthHeaders(),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || 'No se pudo ejecutar el análisis.');
  }

  return response.json();
}
