import { useCallback, useEffect, useState } from "react";
import ConfirmModal from "../components/ConfirmModal";
import Loader from "../components/Loader";
import { getVehicleRegistrationRequests, rejectVehicleRegistrationRequest, approveVehicleRegistrationRequest, getMediaUrl, getBrands, getVehicleTypes } from "../api/plates";
import { listUsers } from "../api/auth";
import SearchBar from "../components/SearchBar";

const emptyForm = { placa: "", propietario_usuario_id: "", marca_id: "", tipo_vehiculo_id: "", color: "" };

export default function VehicleRegistrationRequests() {
  const [requests, setRequests] = useState([]);
  const [brands, setBrands] = useState([]);
  const [types, setTypes] = useState([]);
  const [users, setUsers] = useState([]);
  const [images, setImages] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [confirm, setConfirm] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const [r, b, t, u] = await Promise.all([
        getVehicleRegistrationRequests(),
        getBrands(),
        getVehicleTypes(),
        listUsers()
      ]);
      setRequests(r || []);
      setBrands(b || []);
      setTypes(t || []);
      setUsers((u || []).filter(x => x.rol === "USUARIO"));
      const entries = await Promise.all(
        (r || []).map(async x => [x.id, await getMediaUrl(x.imagen_id).then(v => v.url).catch(() => "")])
      );
      setImages(Object.fromEntries(entries));
    } catch (e) {
      setError(e?.response?.data?.detail || "No se pudieron cargar las solicitudes.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const open = (item) => {
    setSelected(item);
    setForm({
      ...emptyForm,
      placa: item.placa_sugerida,
      propietario_usuario_id: users[0]?.id || "",
      marca_id: brands[0]?.id || "",
      tipo_vehiculo_id: types[0]?.id || "",
      color: item.color_sugerido || ""
    });
    setError("");
  };

  const update = (key, value) => setForm(current => ({ ...current, [key]: value }));

  const approve = async () => {
    if (!form.placa || !form.propietario_usuario_id || !form.marca_id || !form.tipo_vehiculo_id || !form.color.trim()) {
      setError("Completa todos los campos antes de aprobar.");
      return;
    }
    try {
      setSaving(true);
      await approveVehicleRegistrationRequest(selected.id, form);
      setSelected(null);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "No se pudo aprobar la solicitud.");
    } finally {
      setSaving(false);
      setConfirm(null);
    }
  };

  const reject = async () => {
    try {
      setSaving(true);
      await rejectVehicleRegistrationRequest(selected.id);
      setSelected(null);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "No se pudo rechazar la solicitud.");
    } finally {
      setSaving(false);
      setConfirm(null);
    }
  };

  const filteredRequests = requests.filter(item =>
    item.placa_sugerida.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.estado.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) return <Loader label="Cargando solicitudes..." />;

  return (
    <section className="page-stack">
      <div className="hero card">
        <p className="eyebrow">Revisión operativa</p>
        <h2>Solicitudes de registro de vehículos</h2>
        <p className="muted-text">Revisa la evidencia capturada y completa los datos del vehículo.</p>
      </div>

      <SearchBar
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        placeholder="Buscar solicitud por placa..."
        onRefresh={load}
        isRefreshing={loading}
      />

      {error && <p className="error-text">{error}</p>}
      {!filteredRequests.length && (
        <div className="card">
          <p className="muted-text text-center">No se encontraron solicitudes.</p>
        </div>
      )}

      <div style={{ display: "grid", gap: "1rem" }}>
        {filteredRequests.map(item => (
          <article className="card" key={item.id} style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
            {images[item.id] && (
              <img
                src={images[item.id]}
                alt={`Evidencia ${item.placa_sugerida}`}
                style={{ width: 110, height: 80, objectFit: "cover", borderRadius: 10 }}
              />
            )}
            <div style={{ flex: 1, minWidth: 220 }}>
              <p className="eyebrow" style={{ marginBottom: ".25rem" }}>{item.estado}</p>
              <h3 style={{ margin: 0 }}>{item.placa_sugerida}</h3>
              <p className="muted-text" style={{ margin: 0 }}>Confianza OCR: {Math.round(item.confianza_placa * 100)}%</p>
              {item.color_sugerido && <p className="muted-text" style={{ margin: 0 }}>Color sugerido: {item.color_sugerido} ({Math.round((item.confianza_color || 0) * 100)}%)</p>}
            </div>
            <button type="button" onClick={() => open(item)} style={{ padding: ".65rem 1.2rem" }}>
              Revisar
            </button>
          </article>
        ))}
      </div>

      {selected && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={e => { e.preventDefault(); setConfirm({ type: "approve" }); }}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Solicitud pendiente</p>
                <h2>Registrar nuevo vehículo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setSelected(null)}>×</button>
            </div>
            {images[selected.id] && (
              <img
                src={images[selected.id]}
                alt="Evidencia del vehículo"
                style={{ width: "100%", maxHeight: 260, objectFit: "contain", borderRadius: 12, background: "#f1f5f9", marginBottom: "1rem" }}
              />
            )}
            <div className="form-grid">
              <label>Placa
                <input value={form.placa} onChange={e => update("placa", e.target.value.toUpperCase())} required />
              </label>
              <label>Confianza OCR
                <input value={`${Math.round(selected.confianza_placa * 100)}%`} readOnly />
              </label>
              <label>Propietario asociado
                <select value={form.propietario_usuario_id} onChange={e => update("propietario_usuario_id", e.target.value)} required>
                  <option value="">Selecciona un propietario</option>
                  {users.map(u => (
                    <option key={u.id} value={u.id}>{u.nombre} {u.apellido_paterno} — {u.carnet}</option>
                  ))}
                </select>
              </label>
              <label>Marca
                <select value={form.marca_id} onChange={e => update("marca_id", e.target.value)} required>
                  <option value="">Selecciona una marca</option>
                  {brands.map(x => (
                    <option key={x.id} value={x.id}>{x.nombre}</option>
                  ))}
                </select>
              </label>
              <label>Tipo de vehículo
                <select value={form.tipo_vehiculo_id} onChange={e => update("tipo_vehiculo_id", e.target.value)} required>
                  <option value="">Selecciona un tipo</option>
                  {types.map(x => (
                    <option key={x.id} value={x.id}>{x.nombre}</option>
                  ))}
                </select>
              </label>
              <label>Color
                <input value={form.color} onChange={e => update("color", e.target.value)} required />
                <span className="field-hint">Sugerencia automática; verifica y corrige si es necesario.</span>
              </label>
              <label>Confianza del color
                <input value={selected.color_sugerido ? `${Math.round((selected.confianza_color || 0) * 100)}%` : "Sin sugerencia"} readOnly />
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={() => setConfirm({ type: "reject" })} disabled={saving}>Rechazar</button>
              <button type="submit" disabled={saving}>Aprobar</button>
            </div>
          </form>
        </div>
      )}

      {confirm && (
        <ConfirmModal
          isOpen
          title={confirm.type === "approve" ? "Aprobar solicitud" : "Rechazar solicitud"}
          message={confirm.type === "approve" ? `¿Confirmas el registro de ${form.placa}?` : `¿Rechazar la solicitud de ${selected?.placa_sugerida}?`}
          confirmText={confirm.type === "approve" ? "Aprobar" : "Rechazar"}
          confirmColor={confirm.type === "approve" ? "var(--color-primary)" : "#e11d48"}
          loading={saving}
          onCancel={() => setConfirm(null)}
          onConfirm={confirm.type === "approve" ? approve : reject}
        />
      )}
    </section>
  );
}
