import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../Button';
import { runArchivarHallazgos, runInformesRespuesta } from '../../lib/api';

export function SistemaTab() {
  const [running, setRunning] = useState(false);
  const [archivando, setArchivando] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    try {
      await runInformesRespuesta();
      toast.success('Job ejecutado. Revisá los logs del backend o el WhatsApp del auditor para confirmar el envío.');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo ejecutar el job.');
    } finally {
      setRunning(false);
    }
  };

  const handleArchivar = async () => {
    setArchivando(true);
    try {
      const resultado = await runArchivarHallazgos();
      toast.success(
        `${resultado.hallazgos_archivados} hallazgo(s) archivado(s) en ${resultado.sucursales_procesadas} sucursal(es)`
          + (resultado.fallidos ? ` — ${resultado.fallidos} fallaron` : ''),
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'No se pudo ejecutar el job.');
    } finally {
      setArchivando(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="text-xl font-semibold">Circuito de vuelta: informes de respuestas</h2>
        <p className="mt-2 text-sm text-gray-600">
          Agrupa las respuestas de encargados que todavía no se informaron y, para los grupos con más de 45
          minutos sin actividad nueva, genera el PDF con lo detectado vs. lo respondido y se lo manda al auditor
          por WhatsApp. Corre solo cada 15 minutos — este botón lo dispara ahora, sin esperar.
        </p>
        <Button type="button" className="mt-4" isLoading={running} onClick={() => void handleRun()}>
          Ejecutar ahora
        </Button>
      </div>

      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="text-xl font-semibold">Archivar hallazgos sin revisar</h2>
        <p className="mt-2 text-sm text-gray-600">
          Los hallazgos que la IA propone y nadie aprueba ni descarta en 30 días se archivan automáticamente:
          se genera un PDF por sucursal (visible en el detalle de cada sucursal) y salen de "Requiere tu
          decisión". Corre solo una vez al día — este botón lo dispara ahora, sin esperar.
        </p>
        <Button type="button" className="mt-4" isLoading={archivando} onClick={() => void handleArchivar()}>
          Ejecutar ahora
        </Button>
      </div>
    </div>
  );
}
