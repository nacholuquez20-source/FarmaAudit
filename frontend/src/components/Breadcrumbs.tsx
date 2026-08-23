import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  /** Sin `to` = tramo no clickeable (ej. una zona, que no tiene su propia pantalla). */
  to?: string;
}

// Reemplaza los links manuales "← Volver a X" que había en SucursalDetail y
// AuditFichaDetail: esos solo decían de dónde volver, no dónde estás parado
// dentro del módulo. Con 3+ pantallas de profundidad (Sucursales > ficha >
// auditoría) hacía falta un rastro real, no un solo paso atrás.
export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Ruta de navegación" className="mb-4 flex flex-wrap items-center gap-1.5 text-sm">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-gray-300" />}
            {item.to && !isLast ? (
              <Link to={item.to} className="font-medium text-blue-600 hover:text-blue-800">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? 'font-medium text-gray-500' : 'font-medium text-gray-400'}>
                {item.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
