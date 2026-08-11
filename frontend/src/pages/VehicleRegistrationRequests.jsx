import { useCallback, useEffect, useState } from "react";
import ConfirmModal from "../components/ConfirmModal";
import Loader from "../components/Loader";
import { getVehicleRegistrationRequests, rejectVehicleRegistrationRequest, approveVehicleRegistrationRequest, getMediaUrl, getBrands, getVehicleTypes } from "../api/plates";
import { listUsers } from "../api/auth";
import SearchBar from "../components/SearchBar";
import Pagination from "../components/Pagination";

const emptyForm = { placa: "", propietario_usuario_id: "", marca_id: "", tipo_vehiculo_id: "", color: "", color_hex: "" };

const CATALOG_COLORS = {
  "BLANCO": { r: 235, g: 235, b: 235 },
  "NEGRO": { r: 28, g: 28, b: 28 },
  "GRIS": { r: 105, g: 105, b: 105 },
  "PLATEADO": { r: 178, g: 178, b: 178 },
  "ROJO": { r: 190, g: 40, b: 40 },
  "AZUL": { r: 35, g: 85, b: 180 },
  "VERDE": { r: 65, g: 145, b: 65 },
  "AMARILLO": { r: 220, g: 205, b: 35 },
  "MARRON": { r: 115, g: 75, b: 45 },
};

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : null;
}

function getClosestColorName(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return "DESCONOCIDO";

  let closestName = "DESCONOCIDO";
  let minDistance = Infinity;

  Object.entries(CATALOG_COLORS).forEach(([name, catRgb]) => {
    const dist = Math.sqrt(
      Math.pow(rgb.r - catRgb.r, 2) +
      Math.pow(rgb.g - catRgb.g, 2) +
      Math.pow(rgb.b - catRgb.b, 2)
    );
    if (dist < minDistance) {
      minDistance = dist;
      closestName = name;
    }
  });

  return closestName;
}

const translateStatus = (status) => {
  switch (status) {
    case "PENDING":
      return "PENDIENTE";
    case "APPROVED":
      return "APROBADA";
    case "REJECTED":
      return "RECHAZADA";
    default:
      return status;
  }
};

const translateMethod = (method) => {
  switch (String(method).toUpperCase()) {
    case "OPENCV":
      return "OpenCV (Algoritmo local)";
    case "REGRESOR":
      return "Regresor (Red neuronal)";
    case "CLIP":
      return "CLIP (Modelo de respaldo)";
    case "HIBRIDO":
      return "Híbrido (OpenCV + Red)";
    default:
      return method || "No disponible";
  }
};

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
  const [currentPage, setCurrentPage] = useState(1);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

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
    const suggestedColor = item.color_sugerido && item.color_sugerido !== "DESCONOCIDO"
      ? item.color_sugerido
      : "";
    setSelected(item);
    setForm({
      ...emptyForm,
      placa: item.placa_sugerida,
      propietario_usuario_id: users[0]?.id || "",
      marca_id: brands[0]?.id || "",
      tipo_vehiculo_id: types.some(type => type.id === item.tipo_sugerido_id)
        ? item.tipo_sugerido_id
        : "",
      color: suggestedColor,
      color_hex: item.color_hex || ""
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
      setError("");
      setSuccessMessage("");
      await approveVehicleRegistrationRequest(selected.id, form);
      const approvedPlate = form.placa;
      setSelected(null);
      setSuccessMessage(`Solicitud aprobada y vehículo con placa ${approvedPlate} registrado con éxito.`);
      setTimeout(() => setSuccessMessage(""), 5000);
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
      setError("");
      setSuccessMessage("");
      await rejectVehicleRegistrationRequest(selected.id);
      const rejectedPlate = selected.placa_sugerida;
      setSelected(null);
      setSuccessMessage(`Solicitud de registro para la placa ${rejectedPlate} rechazada con éxito.`);
      setTimeout(() => setSuccessMessage(""), 5000);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "No se pudo rechazar la solicitud.");
    } finally {
      setSaving(false);
      setConfirm(null);
    }
  };

  const sortedRequests = [...requests].sort((a, b) => new Date(b.creado_el) - new Date(a.creado_el));

  const filteredRequests = sortedRequests.filter(item =>
    item.placa_sugerida.toLowerCase().includes(searchQuery.toLowerCase()) ||
    translateStatus(item.estado).toLowerCase().includes(searchQuery.toLowerCase())
  );

  const ITEMS_PER_PAGE = 5;
  const totalItems = filteredRequests.length;
  const indexOfLastItem = currentPage * ITEMS_PER_PAGE;
  const indexOfFirstItem = indexOfLastItem - ITEMS_PER_PAGE;
  const currentRequests = filteredRequests.slice(indexOfFirstItem, indexOfLastItem);

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

      {successMessage && <p className="success-text" style={{ padding: "0.75rem", borderRadius: "8px", backgroundColor: "#d1fae5", color: "#065f46" }}>{successMessage}</p>}
      {error && <p className="error-text">{error}</p>}
      {!filteredRequests.length && (
        <div className="card">
          <p className="muted-text text-center">No se encontraron solicitudes.</p>
        </div>
      )}

      <div style={{ display: "grid", gap: "1rem" }}>
        {currentRequests.map(item => (
          <article className="card" key={item.id} style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
            {images[item.id] && (
              <img
                src={images[item.id]}
                alt={`Evidencia ${item.placa_sugerida}`}
                style={{ width: 110, height: 80, objectFit: "cover", borderRadius: 10 }}
              />
            )}
            <div style={{ flex: 1, minWidth: 220 }}>
              <span 
                className="eyebrow" 
                style={{ 
                  display: "inline-block",
                  padding: "0.2rem 0.6rem",
                  borderRadius: "6px",
                  fontSize: "0.7rem",
                  fontWeight: "bold",
                  marginBottom: ".5rem",
                  backgroundColor: item.estado === "PENDING" ? "#fef3c7" : item.estado === "APPROVED" ? "#d1fae5" : "#fee2e2",
                  color: item.estado === "PENDING" ? "#d97706" : item.estado === "APPROVED" ? "#059669" : "#dc2626",
                  textTransform: "uppercase"
                }}
              >
                {translateStatus(item.estado)}
              </span>
              <h3 style={{ margin: 0 }}>{item.placa_sugerida}</h3>
              <p className="muted-text" style={{ margin: 0, marginTop: "0.25rem" }}>
                Confianza OCR: {Math.round(item.confianza_placa * 100)}% &bull; Fecha: {new Date(item.creado_el).toLocaleString("es-BO", { timeZone: "America/La_Paz", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              </p>
            </div>
            <button type="button" onClick={() => open(item)} style={{ padding: ".65rem 1.2rem" }}>
              Revisar
            </button>
          </article>
        ))}
      </div>

      <Pagination
        currentPage={currentPage}
        totalItems={totalItems}
        itemsPerPage={ITEMS_PER_PAGE}
        onPageChange={(page) => setCurrentPage(page)}
      />

      {selected && (() => {
        const isPending = selected.estado === "PENDIENTE";
        return (
          <div className="modal-backdrop">
            <form className="modal-card modal-large registration-form" onSubmit={e => { e.preventDefault(); setConfirm({ type: "approve" }); }}>
              <div className="modal-header">
                <div>
                  <p className="eyebrow">Solicitud {selected.estado.toLowerCase()}</p>
                  <h2>{isPending ? "Registrar nuevo vehículo" : "Detalle de la solicitud"}</h2>
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
              <div className="details-grid">
                <label>Placa
                  <input value={form.placa} onChange={e => update("placa", e.target.value.toUpperCase())} required readOnly={!isPending} />
                </label>
                <label>Confianza OCR
                  <input value={`${Math.round(selected.confianza_placa * 100)}%`} readOnly />
                </label>
                <label>Propietario asociado
                  <select value={form.propietario_usuario_id} onChange={e => update("propietario_usuario_id", e.target.value)} required disabled={!isPending}>
                    <option value="">Selecciona un propietario</option>
                    {users.map(u => (
                      <option key={u.id} value={u.id}>{u.nombre} {u.apellido_paterno} — {u.carnet}</option>
                    ))}
                  </select>
                </label>
                <label>Marca
                  <select value={form.marca_id} onChange={e => update("marca_id", e.target.value)} required disabled={!isPending}>
                    <option value="">Selecciona una marca</option>
                    {brands.map(x => (
                      <option key={x.id} value={x.id}>{x.nombre}</option>
                    ))}
                  </select>
                </label>
                <label>Tipo sugerido por RF-DETR
                  <input
                    value={selected.tipo_sugerido?.nombre || "DESCONOCIDO"}
                    readOnly
                  />
                  <small className="muted-text">
                    Confianza: {selected.confianza_tipo != null
                      ? `${Math.round(selected.confianza_tipo * 100)}%`
                      : "No disponible"}
                  </small>
                </label>
                <label>Tipo confirmado
                  <select value={form.tipo_vehiculo_id} onChange={e => update("tipo_vehiculo_id", e.target.value)} required disabled={!isPending}>
                    <option value="">Selecciona un tipo</option>
                    {types.map(x => (
                      <option key={x.id} value={x.id}>{x.nombre}</option>
                    ))}
                  </select>
                </label>
                <label>Color sugerido
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input value={form.color} onChange={e => update("color", e.target.value.toUpperCase())} required style={{ flex: 1 }} readOnly={!isPending} />
                    <input 
                      type="color" 
                      value={form.color_hex || "#cccccc"} 
                      onChange={e => {
                        const hex = e.target.value;
                        const closest = getClosestColorName(hex);
                        setForm(current => ({
                          ...current,
                          color_hex: hex,
                          color: closest
                        }));
                      }}
                      disabled={!isPending}
                      style={{
                        width: "100px",
                        height: "42px",
                        padding: "2px",
                        border: "1px solid #cbd5e1",
                        borderRadius: "8px",
                        cursor: isPending ? "pointer" : "default",
                        flexShrink: 0
                      }}
                    />
                  </div>
                  <small className="muted-text">
                    {isPending 
                      ? "Sugerencia automática editable; confirma el color observando la evidencia." 
                      : "Color registrado para esta solicitud."}
                  </small>
                </label>
                <label>Confianza del color
                  <input
                    value={selected.confianza_color != null
                      ? `${Math.round(selected.confianza_color * 100)}%`
                      : "No disponible"}
                    readOnly
                  />
                  <small className="muted-text">
                    Método: {translateMethod(selected.metodo_color)}
                  </small>
                </label>
              </div>
              {isPending ? (
                <div className="modal-actions">
                  <button type="button" className="ghost-button" onClick={() => setConfirm({ type: "reject" })} disabled={saving}>Rechazar</button>
                  <button type="submit" disabled={saving}>Aprobar</button>
                </div>
              ) : (
                <div className="modal-actions">
                  <button type="button" className="ghost-button" onClick={() => setSelected(null)}>Cerrar</button>
                </div>
              )}
            </form>
          </div>
        );
      })()}

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
