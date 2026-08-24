import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Check, ImagePlus, MessageCircle, X } from 'lucide-react';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Textarea } from '../components/Textarea';
import { useAuth } from '../hooks/useAuth';
import { useSucursales } from '../hooks/useSucursales';
import { getMarcas, createCampania, createCampaniaAcciones, uploadCampaniaReferencia, activarCampania } from '../lib/api';
import type { CampaniaAccionTipo, Marca } from '../types';

type Step = 1 | 2 | 3;

const ACCION_OPTIONS: { tipo: CampaniaAccionTipo; label: string; hint: string }[] = [
  { tipo: 'exhibicion', label: 'Exhibir productos', hint: 'Puntera, isla o gondola secundaria' },
  { tipo: 'material_pop', label: 'Material POP / cartel', hint: 'Afiche, banner, stopper de gondola' },
  { tipo: 'burbuja_precio', label: 'Burbuja de precio', hint: 'Cartel de precio en el mueble (foto obligatoria)' },
  { tipo: 'descuento_caja', label: 'Descuento en caja', hint: 'Activacion en el sistema de caja (no requiere foto)' },
];

export default function CampaniaWizard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { sucursales, loading: loadingSucursales } = useSucursales();

  const [step, setStep] = useState<Step>(1);
  const [marcas, setMarcas] = useState<Marca[]>([]);
  const [loadingMarcas, setLoadingMarcas] = useState(true);

  // Paso 1
  const [nombre, setNombre] = useState('');
  const [marcaId, setMarcaId] = useState('');
  const [acuerdoDesde, setAcuerdoDesde] = useState('');
  const [acuerdoHasta, setAcuerdoHasta] = useState('');
  const [contraprestacion, setContraprestacion] = useState('');

  // Paso 2
  const [accionesSeleccionadas, setAccionesSeleccionadas] = useState<Set<CampaniaAccionTipo>>(new Set());
  const [accionCustom, setAccionCustom] = useState('');
  // Foto de referencia ("asi debe quedar") opcional por accion, keyeada por tipo
  // ('custom' para la accion personalizada). No aplica a descuento_caja (sin foto).
  const [referenciaFiles, setReferenciaFiles] = useState<Partial<Record<CampaniaAccionTipo, File>>>({});

  // Paso 3
  const [categoriaFilter, setCategoriaFilter] = useState<'' | 'A' | 'B' | 'C'>('');
  const [soloPerfumeria, setSoloPerfumeria] = useState(false);
  const [sucursalesSeleccionadas, setSucursalesSeleccionadas] = useState<Set<string>>(new Set());
  const [showPreview, setShowPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        setLoadingMarcas(true);
        const data = await getMarcas();
        setMarcas(data.filter((marca) => marca.activo));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar marcas');
      } finally {
        setLoadingMarcas(false);
      }
    };
    void load();
  }, []);

  const sucursalesFiltradas = useMemo(
    () =>
      sucursales.filter((sucursal) => {
        if (categoriaFilter && sucursal.categoria !== categoriaFilter) return false;
        if (soloPerfumeria && !sucursal.tiene_perfumeria) return false;
        return true;
      }),
    [sucursales, categoriaFilter, soloPerfumeria],
  );

  const toggleAccion = (tipo: CampaniaAccionTipo) => {
    setAccionesSeleccionadas((current) => {
      const next = new Set(current);
      if (next.has(tipo)) next.delete(tipo);
      else next.add(tipo);
      return next;
    });
  };

  const setReferenciaFile = (tipo: CampaniaAccionTipo, file: File | undefined) => {
    setReferenciaFiles((current) => ({ ...current, [tipo]: file }));
  };

  const toggleSucursal = (id: string) => {
    setSucursalesSeleccionadas((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllFiltradas = () => {
    setSucursalesSeleccionadas((current) => {
      const allSelected = sucursalesFiltradas.length > 0 && sucursalesFiltradas.every((s) => current.has(s.id));
      const next = new Set(current);
      sucursalesFiltradas.forEach((s) => (allSelected ? next.delete(s.id) : next.add(s.id)));
      return next;
    });
  };

  const canGoStep2 = nombre.trim().length > 0 && marcaId.length > 0;
  const canGoStep3 = accionesSeleccionadas.size > 0 || accionCustom.trim().length > 0;
  const canSubmit = sucursalesSeleccionadas.size > 0;

  const previewMessage = `Hola {responsable}, tenes ${accionesSeleccionadas.size + (accionCustom.trim() ? 1 : 0)} tareas nuevas asignadas para la campania ${nombre || '...'}. Respondé este mensaje para verlas.`;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError('');
    try {
      const campania = await createCampania({
        nombre: nombre.trim(),
        marca_id: marcaId,
        acuerdo_desde: acuerdoDesde || null,
        acuerdo_hasta: acuerdoHasta || null,
        contraprestacion: contraprestacion.trim() || null,
        creado_por: user?.id || null,
      });

      const acciones = ACCION_OPTIONS.filter((opcion) => accionesSeleccionadas.has(opcion.tipo)).map((opcion) => ({
        tipo: opcion.tipo,
        descripcion: opcion.label,
      }));
      if (accionCustom.trim()) {
        acciones.push({ tipo: 'custom' as CampaniaAccionTipo, descripcion: accionCustom.trim() });
      }

      // Subir las fotos de referencia (opcionales) antes de crear las acciones: el path
      // se arma con el id de campania + el indice, no con el id de la accion (todavia no existe).
      const accionesConReferencia = await Promise.all(
        acciones.map(async (accion, index) => {
          const file = referenciaFiles[accion.tipo];
          if (!file) return accion;
          const path = await uploadCampaniaReferencia(campania.id, index, file);
          return { ...accion, imagen_referencia_path: path };
        }),
      );

      await createCampaniaAcciones(campania.id, accionesConReferencia);

      const result = await activarCampania(campania.id, Array.from(sucursalesSeleccionadas));
      toast.success(`Campania activada: ${result.tareas_creadas} tareas creadas en ${sucursalesSeleccionadas.size} sucursales.`);
      navigate(`/campanias/${campania.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear la campania.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppLayout title="Nueva campania">
      <div className="mb-6 flex items-center gap-2">
        {[1, 2, 3].map((n) => (
          <div key={n} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
                step >= n ? 'bg-primary-navy text-white' : 'bg-gray-200 text-gray-500'
              }`}
            >
              {step > n ? <Check className="h-4 w-4" /> : n}
            </div>
            {n < 3 && <div className={`h-0.5 w-10 ${step > n ? 'bg-primary-navy' : 'bg-gray-200'}`} />}
          </div>
        ))}
        <span className="ml-3 text-sm font-semibold text-gray-600">
          {step === 1 ? 'Marca y acuerdo' : step === 2 ? 'Acciones sugeridas' : 'Alcance y envio'}
        </span>
      </div>

      {error && (
        <div className="mb-4">
          <FeedbackState title={error} tone="error" />
        </div>
      )}

      {step === 1 && (
        <div className="max-w-2xl rounded-lg bg-white p-6 shadow">
          <label className="mb-4 block text-sm font-medium text-gray-700">
            Nombre de la campania
            <Input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Ej: Unilever Verano 2026"
              className="mt-1"
            />
          </label>

          <div className="mb-4">
            <div className="mb-2 text-sm font-medium text-gray-700">Marca</div>
            {loadingMarcas ? (
              <FeedbackState title="Cargando marcas..." tone="loading" />
            ) : marcas.length === 0 ? (
              <FeedbackState
                title="No hay marcas activas."
                description="Carga una marca en Admin > Marcas (campanas) antes de continuar."
                tone="warning"
              />
            ) : (
              <div className="flex flex-wrap gap-2">
                {marcas.map((marca) => (
                  <button
                    key={marca.id}
                    type="button"
                    onClick={() => setMarcaId(marca.id)}
                    className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                      marcaId === marca.id
                        ? 'border-primary-navy bg-primary-navy text-white'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    {marca.nombre}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium text-gray-700">
              Acuerdo vigente desde
              <Input type="date" value={acuerdoDesde} onChange={(e) => setAcuerdoDesde(e.target.value)} className="mt-1" />
            </label>
            <label className="text-sm font-medium text-gray-700">
              Acuerdo vigente hasta
              <Input type="date" value={acuerdoHasta} onChange={(e) => setAcuerdoHasta(e.target.value)} className="mt-1" />
            </label>
          </div>

          <label className="mb-2 block text-sm font-medium text-gray-700">
            Contraprestacion (opcional)
            <Textarea
              value={contraprestacion}
              onChange={(e) => setContraprestacion(e.target.value)}
              rows={2}
              placeholder="Que recibe la cadena a cambio del espacio (descuento en sell-in, pago directo, etc.)"
              className="mt-1"
            />
          </label>

          <div className="mt-6 flex justify-end">
            <Button disabled={!canGoStep2} onClick={() => setStep(2)}>Continuar</Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="max-w-2xl rounded-lg bg-white p-6 shadow">
          <p className="mb-4 text-sm text-gray-600">
            Elegi las acciones que tienen que ejecutar los responsables de sucursal. "Burbuja de precio" es carteleria
            fisica (se verifica con foto); "Descuento en caja" es una activacion administrativa, no depende del encargado.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {ACCION_OPTIONS.map((opcion) => {
              const active = accionesSeleccionadas.has(opcion.tipo);
              const admiteReferencia = opcion.tipo !== 'descuento_caja';
              const referenciaFile = referenciaFiles[opcion.tipo];
              return (
                <div
                  key={opcion.tipo}
                  className={`rounded-lg border p-4 text-left transition ${
                    active ? 'border-primary-navy bg-primary-navy/5' : 'border-gray-300 bg-white hover:bg-gray-50'
                  }`}
                >
                  <button type="button" onClick={() => toggleAccion(opcion.tipo)} className="block w-full text-left">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-gray-900">{opcion.label}</span>
                      {active && <Check className="h-4 w-4 text-primary-navy" />}
                    </div>
                    <p className="mt-1 text-xs text-gray-500">{opcion.hint}</p>
                  </button>

                  {active && admiteReferencia && (
                    <div className="mt-3 border-t border-primary-navy/10 pt-3">
                      {referenciaFile ? (
                        <div className="flex items-center justify-between text-xs text-gray-600">
                          <span className="truncate">📎 {referenciaFile.name}</span>
                          <button
                            type="button"
                            onClick={() => setReferenciaFile(opcion.tipo, undefined)}
                            className="ml-2 shrink-0 text-gray-400 hover:text-red-600"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-primary-navy">
                          <ImagePlus className="h-3.5 w-3.5" />
                          Foto de referencia (opcional)
                          <input
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={(e) => setReferenciaFile(opcion.tipo, e.target.files?.[0])}
                          />
                        </label>
                      )}
                      <p className="mt-1 text-[11px] text-gray-400">
                        Se le manda al encargado antes de pedirle su foto ("Así debería quedar").
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <label className="mt-4 block text-sm font-medium text-gray-700">
            Accion personalizada (opcional)
            <Input
              value={accionCustom}
              onChange={(e) => setAccionCustom(e.target.value)}
              placeholder="Ej: Degustacion en vidriera"
              className="mt-1"
            />
          </label>

          {accionCustom.trim() && (
            <div className="mt-2">
              {referenciaFiles.custom ? (
                <div className="flex items-center justify-between text-xs text-gray-600">
                  <span className="truncate">📎 {referenciaFiles.custom.name}</span>
                  <button
                    type="button"
                    onClick={() => setReferenciaFile('custom', undefined)}
                    className="ml-2 shrink-0 text-gray-400 hover:text-red-600"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-primary-navy">
                  <ImagePlus className="h-3.5 w-3.5" />
                  Foto de referencia (opcional)
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => setReferenciaFile('custom', e.target.files?.[0])}
                  />
                </label>
              )}
            </div>
          )}

          <div className="mt-6 flex justify-between">
            <Button variant="outline" onClick={() => setStep(1)}>Atras</Button>
            <Button disabled={!canGoStep3} onClick={() => setStep(3)}>Continuar</Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="max-w-3xl rounded-lg bg-white p-6 shadow">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-gray-700">Filtrar sucursales:</span>
            {(['A', 'B', 'C'] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCategoriaFilter((current) => (current === cat ? '' : cat))}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                  categoriaFilter === cat ? 'border-primary-navy bg-primary-navy text-white' : 'border-gray-300 text-gray-700'
                }`}
              >
                Categoria {cat}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setSoloPerfumeria((current) => !current)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                soloPerfumeria ? 'border-primary-navy bg-primary-navy text-white' : 'border-gray-300 text-gray-700'
              }`}
            >
              Solo con perfumeria
            </button>
            <button type="button" onClick={toggleAllFiltradas} className="ml-auto text-xs font-semibold text-primary-navy underline">
              Seleccionar/quitar todas las filtradas
            </button>
          </div>

          {loadingSucursales ? (
            <FeedbackState title="Cargando sucursales..." tone="loading" />
          ) : (
            <div className="max-h-80 overflow-y-auto rounded-lg border border-gray-200">
              {sucursalesFiltradas.length === 0 ? (
                <div className="p-6 text-center text-sm text-gray-500">Ninguna sucursal coincide con el filtro.</div>
              ) : (
                sucursalesFiltradas.map((sucursal) => (
                  <label key={sucursal.id} className="flex items-center gap-3 border-b border-gray-100 px-4 py-2.5 text-sm last:border-b-0 hover:bg-gray-50">
                    <input
                      type="checkbox"
                      checked={sucursalesSeleccionadas.has(sucursal.id)}
                      onChange={() => toggleSucursal(sucursal.id)}
                    />
                    <span className="font-medium text-gray-900">{sucursal.nombre}</span>
                    <span className="text-xs text-gray-400">{sucursal.responsable || 'sin responsable'}</span>
                    {sucursal.tiene_perfumeria && <span className="ml-auto rounded bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700">Perfumeria</span>}
                  </label>
                ))
              )}
            </div>
          )}

          <div className="mt-4">
            <button
              type="button"
              onClick={() => setShowPreview((current) => !current)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-navy"
            >
              <MessageCircle className="h-3.5 w-3.5" />
              {showPreview ? 'Ocultar' : 'Ver'} preview del mensaje de WhatsApp
            </button>
            {showPreview && (
              <div className="mt-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">{previewMessage}</div>
            )}
          </div>

          <div className="mt-6 flex justify-between">
            <Button variant="outline" onClick={() => setStep(2)} disabled={submitting}>Atras</Button>
            <Button disabled={!canSubmit || submitting} isLoading={submitting} onClick={() => void handleSubmit()}>
              Enviar a {sucursalesSeleccionadas.size} sucursale{sucursalesSeleccionadas.size === 1 ? '' : 's'}
            </Button>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
