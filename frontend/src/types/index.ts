export type Role = 'admin' | 'auditor' | 'sucursal';
export type ModulePermission =
  | 'dashboard'
  | 'gestion_desvios'
  | 'revision_desvios'
  | 'mis_desvios'
  | 'sucursales'
  | 'admin'
  | 'campanias'
  | 'mis_campanias';
export type Severidad = 'Alta' | 'Media' | 'Baja';
export type GestionState = 'Abierta' | 'En_proceso' | 'En_revision' | 'En_gestion_terceros' | 'Resuelta' | 'Cerrada' | 'Vencida';
export type SeverityType = Severidad;
export type StatusType = GestionState;
export type DesvioEventoTipo = 'creacion' | 'contacto' | 'respuesta' | 'cierre' | 'nota' | 'evidencia' | 'mensaje' | 'verificacion_auditoria' | 'reincidencia' | 'rechazo';
export type DesvioOrigen = 'auditor' | 'sucursal';
export type NotificacionTipo = 'mensaje_nuevo' | 'encargado_respondio' | 'estado_cambio' | 'vencimiento_proximo' | 'sla_revision_vencido';
export type GestionRevisionAccion = 'aprobar' | 'rechazar' | 'en_gestion_terceros' | 'retomar';
export type AdminTabKey = 'auditores' | 'usuarios' | 'marcas';
export type DashboardView = 'general' | 'zona';
export type SucursalDetailTab = 'reportes' | 'gestiones' | 'stock' | 'auditorias';
export type SucursalEditableField = 'nombre' | 'direccion' | 'zona' | 'responsable' | 'tel_responsable';
export type AutosaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

export interface Sucursal {
  id: string;
  nombre: string;
  direccion: string;
  responsable: string;
  tel_responsable: string;
  zona: string;
  categoria?: string | null;
  tiene_perfumeria?: boolean;
}

export type EstadoSalud = 'critica' | 'atencion' | 'ok';

// Fila de la vista sucursales_dashboard (Centro de Operaciones).
// Métricas precalculadas por la base para el semáforo de salud.
export interface SucursalDashboard {
  id: string;
  nombre: string;
  direccion: string | null;
  zona: string | null;
  categoria: string | null;
  responsable: string | null;
  tel_responsable: string | null;
  tiene_perfumeria: boolean;
  ultima_auditoria: string | null;
  ultimo_score: number | null;
  dias_desde_auditoria: number | null;
  desvios_abiertos: number;
  desvios_vencidos: number;
  estado_salud: EstadoSalud;
}

export interface SucursalUpdate {
  nombre?: string;
  direccion?: string;
  responsable?: string;
  tel_responsable?: string;
  zona?: string;
}

export interface Reporte {
  id: string;
  fecha: string;
  hora: string;
  cuadrilla: string;
  auditor: string;
  id_sucursal: string;
  sucursal: string;
  area: string;
  subitem: string;
  descripcion: string;
  severidad: Severidad;
  foto_url: string | null;
  creado_por_audio: boolean;
  timestamp: string;
}

export interface Gestion {
  id_gestion: string;
  id_reporte: string;
  id_sucursal: string;
  sucursal: string;
  desvio: string;
  severidad: Severidad;
  responsable: string;
  tel_responsable: string;
  plazo_fecha: string;
  plan_accion: string;
  estado: GestionState;
  fecha_cierre: string | null;
  cerrado_por: string | null;
  created_at?: string;
  updated_at?: string;
  plazo_fecha_original?: string | null;
  veces_rechazado?: number;
  en_revision_desde?: string | null;
}

export interface GestionUpdate {
  estado: GestionState;
  cerrado_por?: string;
  fecha_cierre?: string;
}

export interface Desvio extends Gestion {
  area: string;
}

export interface DesvioFilters {
  sucursal: string;
  severidad: '' | Severidad;
  estado: '' | GestionState;
  fechaDesde: string;
  fechaHasta: string;
  search: string;
}

export interface DesvioEvento {
  id: string;
  id_gestion: string;
  tipo: DesvioEventoTipo;
  comentario: string;
  actor_id: string | null;
  actor_nombre: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CreateDesvioEventoInput {
  id_gestion: string;
  tipo: DesvioEventoTipo;
  comentario: string;
  actor_id?: string | null;
  actor_nombre?: string | null;
  metadata?: Record<string, unknown>;
}

export interface EvidenciaStorageMetadata {
  foto_path: string;
  foto_url_signed?: string;
  mime_type: string;
  size_bytes: number;
  origen: DesvioOrigen;
}

export interface DesvioBorradorEvidencia {
  tipo: string;
  path?: string;
  thumb_path?: string;
  url?: string;
  mime_type?: string;
  media_id?: string;
  bucket?: string;
}

export interface DesvioBorrador {
  id: string;
  id_respuesta: string | null;
  id_sesion: string | null;
  id_sucursal: string | null;
  sucursal: string;
  bloque_id: string;
  bloque_nombre: string;
  descripcion: string;
  severidad_sugerida: Severidad;
  estado: 'pendiente' | 'aprobado' | 'descartado' | 'convertido';
  evidencias_json: DesvioBorradorEvidencia[] | null;
  respuesta_consolidada: string | null;
  auditor_nombre: string | null;
  confianza: number | null;
  metadata_json: Record<string, unknown> | null;
  id_reporte: string | null;
  id_gestion: string | null;
  aprobado_por: string | null;
  aprobado_at: string | null;
  descartado_por: string | null;
  descartado_at: string | null;
  razon_descarte: string | null;
  created_at: string;
  updated_at: string;
}

export interface MensajeInternoMetadata {
  origen: DesvioOrigen;
  leido_por_auditor?: boolean;
  leido_por_sucursal?: boolean;
}

export interface Notificacion {
  id: string;
  id_gestion: string;
  user_id: string;
  tipo: NotificacionTipo;
  leida: boolean;
  created_at: string;
}

export interface Auditor {
  telefono: string;
  nombre: string;
  cuadrilla: string;
  activo: boolean;
}

export interface Marca {
  id: string;
  nombre: string;
  activo: boolean;
  created_at?: string;
}

export interface UserProfile {
  id: string;
  email?: string | null;
  role: Role;
  nombre: string | null;
  telefono: string | null;
  /** Responsable de sucursal: id en tabla sucursales (perfumerías). */
  id_sucursal: string | null;
  permisos_modulos?: ModulePermission[] | null;
}

export interface CreatePanelUserInput {
  email: string;
  password: string;
  role: Role;
  nombre: string;
  telefono?: string | null;
  id_sucursal?: string | null;
  permisos_modulos: ModulePermission[];
}

export interface UpdatePanelUserInput {
  email?: string;
  password?: string;
  role?: Role;
  nombre?: string | null;
  telefono?: string | null;
  id_sucursal?: string | null;
  permisos_modulos?: ModulePermission[];
}

export interface DashboardStats {
  total_reportes: number;
  total_desvios: number;
  gestiones_abiertas: number;
  gestiones_vencidas: number;
  gestiones_resueltas: number;
  gestiones_cerradas: number;
  tasa_cierre: number;
  sucursales_sin_auditoria: number;
  /** Severidad Alta y estado aún sin cierre efectivo (Abierta, En proceso o Vencida). */
  criticos_activos: number;
  /** Subconjunto Alta + Vencida. */
  criticos_vencidos: number;
  severidad: {
    alta: number;
    media: number;
    baja: number;
  };
  sucursales_estado: SucursalSupervision[];
  ranking_sucursales: SucursalRanking[];
  tendencia_ultimos_30_dias: TendenciaDia[];
  /** Agregados por zona (maestro sucursales) para vista segmentada. */
  por_zona: ZonaResumen[];
  /** True if showing demo data because database is empty. */
  isDemoData?: boolean;
}

export interface BranchAgg {
  id_sucursal: string;
  sucursal: string;
  zona: string;
  abiertos: number;
  vencidos: number;
  altas: number;
  criticos_activos: number;
  resueltos: number;
  cerrados: number;
  total: number;
}

export interface ControlStockItem {
  id: string;
  auditoria_id: string | null;
  sucursal_id: string;
  fecha: string;
  auditor: string;
  nombre_item: string;
  stock_fisico: number;
  stock_sistema: number;
  diferencia: number;
  alerta: string;
}

export interface ZonaResumen {
  zona: string;
  sucursales: number;
  total_desvios: number;
  abiertos: number;
  vencidos: number;
  criticos_activos: number;
  puntaje_promedio: number;
}

export interface SucursalSupervision {
  id_sucursal: string;
  sucursal: string;
  zona: string;
  abiertos: number;
  vencidos: number;
  altas: number;
  criticos_activos: number;
  resueltos: number;
  cerrados: number;
  total: number;
  /** 0–100, mayor es mejor cumplimiento frente a desvíos/vencidos. */
  puntaje: number;
  semaforo: 'verde' | 'amarillo' | 'rojo';
}

export interface SucursalRanking {
  id_sucursal: string;
  sucursal: string;
  abiertos: number;
  vencidos: number;
  altas: number;
  criticos_activos: number;
}

export interface TendenciaDia {
  fecha: string;
  total: number;
  cerrados: number;
}

export type AuditBloqueId = 'LIMPIEZA' | 'STOCK' | 'OFERTAS' | 'BURBUJAS';

export interface AuditEvidencia {
  id: string;
  tipo: 'foto' | 'audio' | 'texto_manual';
  url?: string;
  contenido?: string;
  duracion?: string;
  timestamp: string;
  asociado_a?: string;
}

export interface AuditDesvio {
  id: string;
  evidencias: AuditEvidencia[];
  descripcion: string;
  timestamp: string;
}

export interface AuditBloque {
  id: AuditBloqueId;
  nombre: string;
  puntuacion: number | null;
  desvios: AuditDesvio[];
  timestamp_inicio?: string;
  timestamp_fin?: string;
}

export interface AuditSession {
  id: string;
  id_sucursal: string;
  sucursal: string;
  auditor_id: string;
  auditor_nombre: string;
  bloques: AuditBloque[];
  estado: 'en_progreso' | 'enviada' | 'procesada';
  timestamp_inicio: string;
  timestamp_fin?: string;
}

// ============ Modulo Campanias (ver ARQUITECTURA_DESVIOS_CAMPANIAS.md, Modulo 2) ============

export type CampaniaEstado = 'Borrador' | 'Activa' | 'En_seguimiento' | 'Finalizada' | 'Cancelada';
export type CampaniaAccionTipo = 'exhibicion' | 'material_pop' | 'burbuja_precio' | 'descuento_caja' | 'custom';
export type CampaniaTareaEstado = 'Pendiente' | 'Completada' | 'Bloqueada_por_insumo' | 'Verificada';
export type CampaniaEventoTipo = 'creacion' | 'vista' | 'completada' | 'evidencia' | 'bloqueo_insumo' | 'rechazo' | 'verificacion' | 'nota';
export type SolicitudInsumoProveedor = 'laboratorio_apm' | 'cadena';
export type SolicitudInsumoEstado = 'Solicitado' | 'Escalado_a_labo' | 'Aprobado' | 'Rechazado' | 'Enviado' | 'Recibido';
export type SolicitudInsumoTipo = 'carteleria' | 'material_pop' | 'stock' | 'otro';

export interface Campania {
  id: string;
  nombre: string;
  marca_id: string;
  estado: CampaniaEstado;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  acuerdo_desde: string | null;
  acuerdo_hasta: string | null;
  contraprestacion: string | null;
  creado_por: string | null;
  created_at: string;
  updated_at: string;
  /** Presente cuando se pide con el join a marcas (ver getCampanias). */
  marcas?: { nombre: string } | null;
}

export interface CampaniaAccion {
  id: string;
  campania_id: string;
  tipo: CampaniaAccionTipo;
  descripcion: string | null;
  requiere_foto: boolean;
  verificable_por_foto: boolean;
  created_at?: string;
}

export interface CampaniaTarea {
  id: string;
  campania_id: string;
  accion_id: string;
  id_sucursal: string;
  responsable: string | null;
  tel_responsable: string | null;
  estado: CampaniaTareaEstado;
  vista_at: string | null;
  plazo_fecha: string | null;
  evidencia_path: string | null;
  created_at: string;
  updated_at: string;
  /** Presentes cuando se piden con join (ver getCampaniaTareas / getMisCampaniaTareas). */
  campania_acciones?: CampaniaAccion | null;
  sucursales?: { nombre: string } | null;
  campanias?: { nombre: string; estado: CampaniaEstado; marcas?: { nombre: string } | null } | null;
}

export interface CampaniaEvento {
  id: string;
  tarea_id: string;
  tipo: CampaniaEventoTipo;
  comentario: string | null;
  actor_id: string | null;
  actor_nombre: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface SolicitudInsumo {
  id: string;
  tarea_id: string;
  tipo_insumo: SolicitudInsumoTipo;
  detalle: string | null;
  cantidad: string | null;
  proveedor: SolicitudInsumoProveedor;
  estado: SolicitudInsumoEstado;
  contacto_trade: string | null;
  aprobado_por: string | null;
  created_at: string;
  updated_at: string;
}

export interface CampaniaResultado {
  id: string;
  campania_id: string;
  id_sucursal: string;
  venta_periodo_campania: number | null;
  venta_periodo_base: number | null;
  unidad: 'unidades' | 'pesos';
  cargado_por: string | null;
  created_at: string;
}
