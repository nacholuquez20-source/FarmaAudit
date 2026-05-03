import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppLayout } from '../components/AppLayout';
import { FeedbackState } from '../components/FeedbackState';
import { useSucursales } from '../hooks/useSucursales';
import { useAuth } from '../hooks/useAuth';

export default function Sucursales() {
  const { role, profile } = useAuth();
  const { sucursales, loading, error } = useSucursales();
  const [searchText, setSearchText] = useState('');
  const navigate = useNavigate();

  const filteredSucursales = sucursales.filter(
    (sucursal) =>
      sucursal.nombre.toLowerCase().includes(searchText.toLowerCase()) ||
      sucursal.responsable.toLowerCase().includes(searchText.toLowerCase()) ||
      sucursal.zona.toLowerCase().includes(searchText.toLowerCase())
  );

  const lista =
    role === 'sucursal' && profile?.id_sucursal
      ? filteredSucursales.filter((s) => s.id === profile.id_sucursal)
      : filteredSucursales;

  if (loading) {
    return (
      <AppLayout title="Sucursales">
        <FeedbackState title="Cargando sucursales..." />
      </AppLayout>
    );
  }

  return (
    <AppLayout title={role === 'sucursal' ? 'Mi sucursal' : 'Sucursales'}>
      {role === 'sucursal' && !profile?.id_sucursal && (
        <div className="mb-4">
          <FeedbackState
            title="Tu usuario no tiene sucursal asignada."
            description="Pedí al administrador que vincule tu perfil en Administración."
            tone="error"
          />
        </div>
      )}
      {error && <div className="mb-4"><FeedbackState title={error} tone="error" /></div>}

      <div className="mb-6">
        <input
          type="text"
          placeholder={role === 'sucursal' ? 'Buscar en tu sucursal...' : 'Buscar perfumerías...'}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-100 border-b">
            <tr>
              <th className="text-left px-6 py-3 font-semibold">Nombre</th>
              <th className="text-left px-6 py-3 font-semibold">Zona</th>
              <th className="text-left px-6 py-3 font-semibold">Responsable</th>
              <th className="text-left px-6 py-3 font-semibold">Telefono</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((sucursal) => (
              <tr
                key={sucursal.id}
                onClick={() => navigate(`/sucursales/${sucursal.id}`)}
                className="border-b hover:bg-gray-50 cursor-pointer transition"
              >
                <td className="px-6 py-4 font-medium">{sucursal.nombre}</td>
                <td className="px-6 py-4 text-gray-600">{sucursal.zona}</td>
                <td className="px-6 py-4 text-gray-600">{sucursal.responsable}</td>
                <td className="px-6 py-4 text-gray-600">{sucursal.tel_responsable}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {lista.length === 0 && (
        <div className="mt-4">
          <FeedbackState title="No se encontraron farmacias" />
        </div>
      )}
    </AppLayout>
  );
}
