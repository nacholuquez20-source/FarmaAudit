import { CheckCircle2, MessageCircle, Camera, MapPin } from 'lucide-react';
import type { Sucursal } from '../types';

interface AuditStep {
  id: string;
  label: string;
  completed: boolean;
  icon: React.ReactNode;
}

interface WhatsAppAuditFlowProps {
  sucursal: Sucursal;
  onStartAudit: () => void;
  steps?: AuditStep[];
}

export function WhatsAppAuditFlow({
  sucursal,
  onStartAudit,
  steps,
}: WhatsAppAuditFlowProps) {
  const defaultSteps: AuditStep[] = steps || [
    {
      id: 'select',
      label: 'Sucursal seleccionada',
      completed: true,
      icon: <MapPin className="w-5 h-5" />,
    },
    {
      id: 'score',
      label: 'Responder cuestionario de auditoría',
      completed: false,
      icon: <MessageCircle className="w-5 h-5" />,
    },
    {
      id: 'evidence',
      label: 'Enviar fotos de desvíos',
      completed: false,
      icon: <Camera className="w-5 h-5" />,
    },
    {
      id: 'confirm',
      label: 'Auditoría completada',
      completed: false,
      icon: <CheckCircle2 className="w-5 h-5" />,
    },
  ];

  const whatsappPhone = import.meta.env.VITE_WHATSAPP_PHONE || '5493816199195';
  const message = encodeURIComponent(
    `Hola, quiero hacer la auditoría de ${sucursal.nombre} (${sucursal.id}). ¿Cómo procedo?`
  );
  const whatsappUrl = `https://wa.me/${whatsappPhone}?text=${message}`;

  return (
    <div className="space-y-6">
      {/* Sucursal Info */}
      <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg border border-green-200 p-6">
        <div className="flex items-start gap-4">
          <div className="bg-green-100 rounded-full p-3">
            <MapPin className="w-6 h-6 text-green-700" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900">{sucursal.nombre}</h3>
            <p className="text-sm text-gray-600 mt-1">
              Zona: {sucursal.zona}
            </p>
            <p className="text-sm text-gray-600">
              Responsable: {sucursal.responsable || 'Sin asignar'}
            </p>
          </div>
        </div>
      </div>

      {/* Steps Flow */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-6">Flujo de Auditoría</h3>

        <div className="space-y-4">
          {defaultSteps.map((step, index) => (
            <div key={step.id}>
              <div className="flex items-start gap-4">
                {/* Icon */}
                <div
                  className={`flex-shrink-0 p-3 rounded-full transition ${
                    step.completed
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}
                >
                  {step.completed ? (
                    <CheckCircle2 className="w-5 h-5" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-current" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 pt-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`font-medium text-sm ${
                        step.completed ? 'text-green-700' : 'text-gray-700'
                      }`}
                    >
                      {step.label}
                    </span>
                    {step.completed && (
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                        ✓ Completado
                      </span>
                    )}
                  </div>
                </div>

                {/* Step Number */}
                <div className="text-xs font-semibold text-gray-500 pt-1">
                  {index + 1}/{defaultSteps.length}
                </div>
              </div>

              {/* Divider */}
              {index < defaultSteps.length - 1 && (
                <div className="ml-6 h-8 border-l-2 border-gray-200 my-2" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* WhatsApp Audit Option */}
      <div className="bg-green-50 rounded-lg border border-green-200 p-6">
        <div className="flex items-start gap-3 mb-4">
          <MessageCircle className="w-5 h-5 text-green-700 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-gray-900 text-sm">Opción: Auditoría por WhatsApp</h4>
            <p className="text-sm text-gray-600 mt-1">
              Responde el cuestionario directamente en WhatsApp y envía las fotos de los desvíos.
              Recibirás confirmación al completar.
            </p>
          </div>
        </div>

        <a
          href={whatsappUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition font-medium text-sm"
        >
          <MessageCircle className="w-4 h-4" />
          Iniciar auditoría por WhatsApp
        </a>
      </div>

      {/* Web Audit Option */}
      <div className="bg-blue-50 rounded-lg border border-blue-200 p-6">
        <div className="flex items-start gap-3 mb-4">
          <Camera className="w-5 h-5 text-blue-700 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-gray-900 text-sm">Opción: Auditoría Web</h4>
            <p className="text-sm text-gray-600 mt-1">
              Completa la auditoría en esta plataforma con interfaz mejorada, fotos de mejor calidad
              y resumen visual antes de enviar.
            </p>
          </div>
        </div>

        <button
          onClick={onStartAudit}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium text-sm"
        >
          <Camera className="w-4 h-4" />
          Iniciar auditoría Web
        </button>
      </div>
    </div>
  );
}
