export type Role = 'admin' | 'auditor';
export type Severidad = 'Alta' | 'Media' | 'Baja';
export type GestionState = 'Abierta' | 'En_proceso' | 'Resuelta' | 'Cerrada' | 'Vencida';
export type DesvioEventoTipo = 'creacion' | 'contacto' | 'respuesta' | 'cierre' | 'nota' | 'evidencia';

export interface Sucursal {
  id: string;
  nombre: string;
  direccion: string;
  responsable: string;
  tel_responsable: string;
  zona: string;
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

export interface Auditor {
  telefono: string;
  nombre: string;
  cuadrilla: string;
  activo: boolean;
}

export interface UserProfile {
  id: string;
  role: Role;
  nombre: string | null;
  telefono: string | null;
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
  severidad: {
    alta: number;
    media: number;
    baja: number;
  };
  sucursales_estado: SucursalSupervision[];
  ranking_sucursales: SucursalRanking[];
  tendencia_ultimos_30_dias: TendenciaDia[];
}

export interface SucursalSupervision {
  id_sucursal: string;
  sucursal: string;
  abiertos: number;
  vencidos: number;
  altas: number;
  resueltos: number;
  cerrados: number;
  total: number;
  semaforo: 'verde' | 'amarillo' | 'rojo';
}

export interface SucursalRanking {
  id_sucursal: string;
  sucursal: string;
  abiertos: number;
  vencidos: number;
  altas: number;
}

export interface TendenciaDia {
  fecha: string;
  total: number;
  cerrados: number;
}
