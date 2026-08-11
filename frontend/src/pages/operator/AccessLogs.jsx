import { useEffect, useState } from "react";
import Loader from "../../components/Loader";
import { getAccessLogs, createAutoAccessLog, getMediaUrl, getMyVehicles } from "../../api/plates";
import { useAuth } from "../../hooks/useAuth";
import Pagination from "../../components/Pagination";
import ConfirmModal from "../../components/ConfirmModal";
import SearchBar from "../../components/SearchBar";

function AccessLogs() {
  const { user } = useAuth();
  const isStaff = user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR";
  const [logs, setLogs] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [logsSearchQuery, setLogsSearchQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selectedEvidenceUrl, setSelectedEvidenceUrl] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);

  const viewEvidence = async (mediaId) => {
    try {
      setEvidenceLoading(true);
      const result = await getMediaUrl(mediaId);
      setSelectedEvidenceUrl(result.url);
    } catch (err) {
      setError(err?.response?.data?.detail || "La evidencia no esta disponible.");
    } finally {
      setEvidenceLoading(false);
    }
  };

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;
  const [confirmConfig, setConfirmConfig] = useState({ isOpen: false, title: "", message: "", onConfirm: null, confirmColor: "#e11d48" });

  const [showModal, setShowModal] = useState(false);
  const [searchPlate, setSearchPlate] = useState("");
  const [formData, setFormData] = useState({
    vehicle_id: "",
    direction: "ENTRY",
    zone: "Portería Principal",
    notes: ""
  });

  const fetchData = async (isManual = false) => {
    try {
      if (isManual) setIsRefreshing(true);
      else setLoading(true);
      const [logsData, vehiclesData] = await Promise.all([
        getAccessLogs(),
        getMyVehicles()
      ]);
      setLogs(logsData || []);
      setVehicles(vehiclesData || []);
    } catch (err) {
      setError("No se pudo cargar la información de accesos.");
      console.error(err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (user?.id) {
      fetchData();
    }
  }, [user?.id]);

  const handleOpenModal = () => {
    setFormData({
      vehicle_id: vehicles[0]?.id || "",
      direction: "ENTRY",
      zone: "Portería Principal",
      notes: ""
    });
    setSearchPlate("");
    setError("");
    setSuccess("");
    setShowModal(true);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.vehicle_id) {
      setError("Debes seleccionar un vehículo.");
      return;
    }

    const dirLabel = formData.direction === "ENTRY" ? "Ingreso" : "Salida";
    setConfirmConfig({
      isOpen: true,
      title: "Registrar Acceso Manual",
      message: `¿Confirmas registrar un ${dirLabel} manual para este vehículo?`,
      confirmColor: "var(--color-primary)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          setError("");
          setSuccess("");
          await createAutoAccessLog({
            vehicle_id: formData.vehicle_id,
            zone: formData.zone,
            notes: formData.notes,
            direction: formData.direction
          });
          setSuccess("Acceso registrado correctamente.");
          setShowModal(false);
          fetchData();
        } catch (err) {
          setError(err?.response?.data?.detail || err?.message || "No se pudo registrar el acceso.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  if (loading) {
    return <Loader label="Cargando historial de accesos..." />;
  }

  const filteredLogs = logs.filter(log => {
    const query = logsSearchQuery.toLowerCase();
    const plate = log.vehicle?.license_plate?.toLowerCase() || "";
    const direction = (log.direction === "ENTRY" ? "ingreso" : "salida").toLowerCase();
    const zone = log.zone?.toLowerCase() || "";
    const ownerName = log.vehicle?.owner?.full_name?.toLowerCase() || "";
    const vehicleName = `${log.vehicle?.brand || ""} ${log.vehicle?.model || ""}`.toLowerCase();
    return plate.includes(query) || direction.includes(query) || zone.includes(query) || ownerName.includes(query) || vehicleName.includes(query);
  });

  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentLogs = filteredLogs.slice(indexOfFirstItem, indexOfLastItem);

  return (
    <section className="page-stack">
      <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
        <div>
          <p className="eyebrow">Telemetría</p>
          <h3>Registros de Entrada y Salida</h3>
        </div>
        {isStaff && (
          <button type="button" onClick={handleOpenModal} style={{ padding: "0.6rem 1.2rem" }}>
            Registrar Acceso Manual
          </button>
        )}
      </div>

      {success && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}><p style={{ color: "green", fontWeight: "bold", background: "#e6ffe6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid green", display: "inline-block", margin: 0 }}>{success}</p></div>}
      {error && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}><p className="error-text" style={{ background: "#ffe6e6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid red", display: "inline-block", margin: 0 }}>{error}</p></div>}

      <SearchBar
        searchQuery={logsSearchQuery}
        setSearchQuery={(val) => { setLogsSearchQuery(val); setCurrentPage(1); }}
        placeholder="Buscar accesos por placa, dirección, zona o propietario..."
        onRefresh={fetchData}
        isRefreshing={isRefreshing}
      />

      <div className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
              <th style={{ padding: "1rem" }}>Fecha / Hora</th>
              <th style={{ padding: "1rem" }}>Placa</th>
              <th style={{ padding: "1rem" }}>Dirección</th>
              <th style={{ padding: "1rem" }}>Zona / Portería</th>
              <th style={{ padding: "1rem" }}>Vehículo</th>
              <th style={{ padding: "1rem" }}>Propietario</th>
              <th style={{ padding: "1rem" }}>Notas</th>
              <th style={{ padding: "1rem" }}>Evidencia</th>
            </tr>
          </thead>
          <tbody>
            {currentLogs.map((log) => (
              <tr key={log.id} style={{ borderBottom: "1px solid rgba(21, 62, 117, 0.05)" }}>
                <td style={{ padding: "1rem", fontWeight: "bold" }}>
                  {new Date(log.timestamp).toLocaleString("es-BO", { timeZone: "America/La_Paz", hour12: false })}
                </td>
                <td style={{ padding: "1rem", fontFamily: "monospace", fontSize: "1.1rem", fontWeight: "bold", color: "#153e75" }}>
                  {log.vehicle?.license_plate}
                </td>
                <td style={{ padding: "1rem" }}>
                  <span style={{
                    padding: "0.25rem 0.5rem",
                    borderRadius: "4px",
                    fontSize: "0.75rem",
                    fontWeight: "bold",
                    background: log.direction === "ENTRY" ? "#e6ffe6" : "#fff2e6",
                    color: log.direction === "ENTRY" ? "green" : "#d46b08"
                  }}>
                    {log.direction === "ENTRY" ? "INGRESO" : "SALIDA"}
                  </span>
                </td>
                <td style={{ padding: "1rem" }}>{log.zone}</td>
                <td style={{ padding: "1rem" }}>
                  {log.vehicle?.brand} {log.vehicle?.model} ({log.vehicle?.color})
                </td>
                <td style={{ padding: "1rem" }}>
                  {log.vehicle?.owner?.full_name || "Sin propietario"}
                </td>
                <td style={{ padding: "1rem", color: "#666", fontSize: "0.9rem" }}>
                  {log.notes || "-"}
                </td>
                <td style={{ padding: "1rem" }}>
                  {log.image_status === "READY" ? (
                    <button type="button" className="ghost-button" onClick={() => viewEvidence(log.image_id)}>Ver</button>
                  ) : log.image_status === "FAILED" ? "Fallida" : log.image_status === "PROCESSING" ? "Procesando" : log.image_status === "PENDING" ? "Pendiente" : "-"}
                </td>
              </tr>
            ))}
             {!filteredLogs.length && (
              <tr>
                <td colSpan="8" style={{ padding: "2rem", textAlign: "center", color: "#666" }}>
                  No se encontraron movimientos con ese filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {!loading && filteredLogs.length > 0 && (
        <Pagination
          currentPage={currentPage}
          totalItems={filteredLogs.length}
          itemsPerPage={itemsPerPage}
          onPageChange={setCurrentPage}
        />
      )}

      {showModal && (
        <div className="modal-backdrop">
          <form className="modal-card" onSubmit={handleSubmit}>
            <div className="modal-header">
              <h2>Registrar Acceso Vehicular</h2>
              <button type="button" className="ghost-button" onClick={() => setShowModal(false)}>
                Cerrar
              </button>
            </div>

            <div className="form-block" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <label className="field-group">
                <span>Buscar por Placa</span>
                <input
                  type="text"
                  placeholder="Escribe la placa para filtrar..."
                  value={searchPlate}
                  onChange={(e) => {
                    const term = e.target.value.toUpperCase();
                    setSearchPlate(term);
                    // Preseleccionar si hay una sola coincidencia exacta
                    const matched = vehicles.find(v => v.placa === term);
                    if (matched) {
                      setFormData(curr => ({ ...curr, vehicle_id: matched.id }));
                    }
                  }}
                  style={{
                    padding: "0.6rem 0.8rem",
                    borderRadius: "8px",
                    border: "1px solid rgba(21, 62, 117, 0.2)",
                    fontSize: "0.95rem"
                  }}
                />
              </label>

              <label className="field-group">
                <span>Seleccionar Vehículo</span>
                <select
                  value={formData.vehicle_id}
                  onChange={(e) => setFormData((curr) => ({ ...curr, vehicle_id: e.target.value }))}
                  required
                >
                  <option value="">-- Selecciona un Vehículo Autorizado --</option>
                  {vehicles
                    .filter(v => v.placa && v.placa.toUpperCase().includes(searchPlate))
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.placa} - {v.marca?.nombre || "Sin marca"} ({v.propietario ? `${v.propietario.nombre} ${v.propietario.apellido_paterno}` : "Sin propietario"})
                      </option>
                    ))}
                </select>
              </label>

              <label className="field-group">
                <span>Movimiento</span>
                <select
                  value={formData.direction}
                  onChange={(e) => setFormData((curr) => ({ ...curr, direction: e.target.value }))}
                  required
                >
                  <option value="ENTRY">Ingreso</option>
                  <option value="EXIT">Salida</option>
                </select>
              </label>

              <label className="field-group">
                <span>Zona / Portería de Control</span>
                <input
                  type="text"
                  placeholder="Portería Principal / Parqueo de Tecnología"
                  value={formData.zone}
                  onChange={(e) => setFormData((curr) => ({ ...curr, zone: e.target.value }))}
                  required
                />
              </label>

              <label className="field-group">
                <span>Observaciones</span>
                <textarea
                  placeholder="Ej. Ingreso de visita, portón auxiliar..."
                  value={formData.notes}
                  onChange={(e) => setFormData((curr) => ({ ...curr, notes: e.target.value }))}
                />
              </label>
            </div>

            <div className="modal-actions" style={{ marginTop: "1.5rem" }}>
              <button type="submit" disabled={saving}>
                {saving ? "Registrando..." : "Confirmar Movimiento"}
              </button>
            </div>
          </form>
        </div>
      )}

      <ConfirmModal
        isOpen={confirmConfig.isOpen}
        title={confirmConfig.title}
        message={confirmConfig.message}
        confirmColor={confirmConfig.confirmColor}
        onConfirm={confirmConfig.onConfirm}
        onCancel={() => setConfirmConfig({ ...confirmConfig, isOpen: false })}
      />
      {/* Modal para visualizar la evidencia */}
      {(selectedEvidenceUrl || evidenceLoading) && (
        <div 
          className="modal-backdrop" 
          onClick={() => setSelectedEvidenceUrl(null)}
          style={{ zIndex: 100 }}
        >
          <div 
            className="modal-card" 
            onClick={(e) => e.stopPropagation()}
            style={{ 
              maxWidth: "700px", 
              width: "90%", 
              padding: "1.5rem", 
              borderRadius: "16px",
              background: "#ffffff"
            }}
          >
            <div className="modal-header" style={{ marginBottom: "1rem" }}>
              <div>
                <p className="eyebrow" style={{ textTransform: "uppercase" }}>Bitácora de Acceso</p>
                <h2 style={{ fontSize: "1.45rem", color: "#1e3a8a" }}>Evidencia de Detección</h2>
              </div>
              <button 
                type="button" 
                className="ghost-button" 
                onClick={() => setSelectedEvidenceUrl(null)}
                style={{ padding: "0.5rem 1rem" }}
              >
                Cerrar
              </button>
            </div>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", width: "100%", background: "#f1f5f9", borderRadius: "12px", overflow: "hidden", minHeight: "350px", maxHeight: "70vh", position: "relative" }}>
              {evidenceLoading ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", alignItems: "center" }}>
                  <span style={{ fontSize: "1.2rem", fontWeight: "bold", color: "#1e3a8a" }}>Cargando evidencia...</span>
                </div>
              ) : (
                <img 
                  src={selectedEvidenceUrl} 
                  alt="Evidencia del Acceso" 
                  style={{ 
                    maxWidth: "100%", 
                    maxHeight: "70vh", 
                    objectFit: "contain",
                    display: "block" 
                  }} 
                />
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default AccessLogs;


