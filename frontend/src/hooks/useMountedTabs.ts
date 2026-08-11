import { useCallback, useState } from 'react';

/**
 * Mantiene montada toda pestaña ya visitada, para que volver a ella no
 * dispare otra vez su carga de datos (los paneles de desvíos, por ejemplo,
 * piden las gestiones y los eventos de cada una).
 *
 * Se lleva en estado y no en un ref a propósito: leer `ref.current` durante el
 * render es lo que marca la regla `react-hooks/refs`, y además rompe con el
 * React Compiler.
 */
export function useMountedTabs<T extends string>(active: T) {
  const [visited, setVisited] = useState<Set<T>>(() => new Set([active]));

  const markVisited = useCallback((tab: T) => {
    setVisited((current) => (current.has(tab) ? current : new Set(current).add(tab)));
  }, []);

  // `active` cubre el caso de llegar por URL o por el botón atrás a una
  // pestaña que todavía no se había visitado con un click.
  const isMounted = useCallback(
    (tab: T) => visited.has(tab) || active === tab,
    [visited, active],
  );

  return { isMounted, markVisited };
}
