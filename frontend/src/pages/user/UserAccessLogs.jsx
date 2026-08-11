import { useEffect, useState, useCallback } from "react";
import Loader from "../../components/Loader";
import { getAccessLogs, getMediaUrl } from "../../api/plates";
import { useAuth } from "../../hooks/useAuth";
import Pagination from "../../components/Pagination";

function UserAccessLogs() {
  const { user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [selectedEvidenceUrl, setSelectedEvidenceUrl] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const loadLogs = useCallback(async (quiet = false) => {
    try {
      if (!quiet) setLoading(true);
      else setIsRefreshing(true);
      setError("");

      const logsData = await getAccessLogs();
      setLogs(logsData || []);
    } catch (err) {
      console.error("Error al cargar la bitácora de accesos:", err);
      setError("No se pudo cargar tu historial de accesos.");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const handleViewEvidence = async (mediaId) => {
    try {
      setEvidenceLoading(true);
      const result = await getMediaUrl(mediaId);
      setSelectedEvidenceUrl(result.url);
    } catch (err) {
      console.error(err);
      alert("No se pudo cargar la imagen de evidencia.");
    } finally {
      setEvidenceLoading(false);
    }
  };

  // Paginación
  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentLogs = logs.slice(indexOfFirstItem, indexOfLastItem);

  if (loading) {
    return <Loader label="Cargando tu historial de accesos..." />;
  }

  return (
    <section className="card page-stack" style={{ background: "transparent", border: "none", boxShadow: "none", padding: 0 }}>
      {error && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}><p className="error-text" style={{ background: "#ffe6e6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid red", display: "inline-block", margin: 0 }}>{error}</p></div>}

      <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "2rem" }}>
        <div>
          <p className="eyebrow" style={{ textTransform: "uppercase", fontSize: "0.75rem", letterSpacing: "0.08em", fontWeight: "bold", color: "#64748b" }}>Telemetría</p>
          <h2 style={{ fontSize: "1.75rem", fontWeight: "700", color: "#1e3a8a", margin: "0.25rem 0 0 0" }}>Mis Registros de Entrada y Salida</h2>
        </div>
        <button 
          type="button" 
          className="ghost-button" 
          onClick={() => loadLogs(true)} 
          disabled={isRefreshing}
          style={{ padding: "0.6rem", display: "flex", alignItems: "center", justifyContent: "center", width: "40px", height: "40px", borderRadius: "8px" }} 
          title="Refrescar historial"
        >
          {isRefreshing ? (
            <span style={{ fontSize: "0.8rem", color: "#64748b" }}>...</span>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.59-9.21l5.67-5.67"/></svg>
          )}
        </button>
      </div>

      {!logs.length ? (
        <div className="card" style={{ padding: "3rem 1.5rem", textAlign: "center", borderRadius: "16px", background: "#ffffff", border: "1px solid rgba(21, 62, 117, 0.08)" }}>
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ color: "#94a3b8", marginBottom: "1rem" }}><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>
          <p className="muted-text" style={{ fontSize: "1.1rem" }}>No se registran movimientos de tus vehículos en el sistema todavía.</p>
        </div>
      ) : (
        <>
          {/* Línea de tiempo vertical premium */}
          <div style={{ position: "relative", paddingLeft: "2.5rem", borderLeft: "2.5px solid #e2e8f0", margin: "1rem 0.5rem 2rem 1.5rem" }}>
            {currentLogs.map((log) => {
              const isEntry = log.direction === "ENTRY" || log.direction === "ENTRADA" || (log.direction || "").toUpperCase().includes("ENT");
              
              // Formateo de fecha y hora
              const dateObj = new Date(log.timestamp);
              const formattedTime = dateObj.toLocaleTimeString("es-BO", { timeZone: "America/La_Paz", hour: "2-digit", minute: "2-digit", second: "2-digit" });
              const formattedDate = dateObj.toLocaleDateString("es-BO", { timeZone: "America/La_Paz", day: "2-digit", month: "long", year: "numeric" });

              return (
                <div 
                  key={log.id} 
                  style={{ 
                    position: "relative", 
                    marginBottom: "2rem"
                  }}
                >
                  {/* Punto indicador de la línea de tiempo */}
                  <div 
                    style={{
                      position: "absolute",
                      left: "calc(-2.5rem - 11px)",
                      top: "12px",
                      width: "20px",
                      height: "20px",
                      borderRadius: "50%",
                      background: isEntry ? "#22c55e" : "#3b82f6",
                      border: "4px solid #ffffff",
                      boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
                      zIndex: 2
                    }}
                  />

                  {/* Tarjeta del Log */}
                  <div 
                    className="card"
                    style={{
                      padding: "1.25rem 1.5rem",
                      borderRadius: "14px",
                      border: "1px solid rgba(21, 62, 117, 0.06)",
                      background: "#ffffff",
                      boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.03)",
                      display: "flex",
                      flexWrap: "wrap",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: "1.25rem",
                      transition: "transform 0.15s, box-shadow 0.15s"
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = "translateX(4px)";
                      e.currentTarget.style.boxShadow = "0 8px 12px -3px rgba(0,0,0,0.06)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = "translateX(0)";
                      e.currentTarget.style.boxShadow = "0 4px 6px -1px rgba(0, 0, 0, 0.03)";
                    }}
                  >
                    {/* Sección Izquierda: Dirección, Fecha y Portería */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        {/* Badge de Dirección */}
                        <span 
                          style={{
                            background: isEntry ? "#e8f5e9" : "#e3f2fd",
                            color: isEntry ? "#1b5e20" : "#0d47a1",
                            padding: "0.25rem 0.75rem",
                            borderRadius: "20px",
                            fontSize: "0.75rem",
                            fontWeight: "700",
                            letterSpacing: "0.05em",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.25rem"
                          }}
                        >
                          {isEntry ? (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
                          ) : (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>
                          )}
                          {isEntry ? "INGRESO" : "SALIDA"}
                        </span>

                        <span style={{ fontSize: "0.85rem", color: "#64748b", fontWeight: "500" }}>
                          {formattedDate} - {formattedTime}
                        </span>
                      </div>

                      {/* Portería */}
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "#475569", fontSize: "0.95rem" }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "#64748b" }}><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
                        <span>Zona: <strong>{log.zone || "Portería Principal"}</strong></span>
                      </div>
                    </div>

                    {/* Sección Central: Placa e Info de Vehículo */}
                    <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", flexWrap: "wrap" }}>
                      {/* Faux Placa */}
                      <div 
                        style={{
                          background: "#ffffff",
                          border: "2px solid #1e3a8a",
                          borderRadius: "4px",
                          padding: "1px",
                          width: "110px",
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center"
                        }}
                      >
                        <div style={{ background: "#1e3a8a", color: "#ffffff", width: "100%", fontSize: "0.45rem", textAlign: "center", fontWeight: "bold", letterSpacing: "0.1em" }}>BOLIVIA</div>
                        <span style={{ fontFamily: "monospace", fontSize: "0.95rem", fontWeight: "900", color: "#1e293b", letterSpacing: "1px" }}>
                          {log.vehicle?.placa || log.placa || "S/P"}
                        </span>
                      </div>

                      {/* Detalles del vehículo */}
                      <div style={{ fontSize: "0.9rem", color: "#475569" }}>
                        <div>{log.vehicle?.marca?.nombre || "Marca Desconocida"}</div>
                        <div style={{ fontSize: "0.8rem", color: "#64748b" }}>{log.vehicle?.color || "Color no esp."}</div>
                      </div>
                    </div>

                    {/* Sección Derecha: Evidencia */}
                    <div>
                      {log.image_id || log.media_id ? (
                        <button
                          type="button"
                          onClick={() => handleViewEvidence(log.image_id || log.media_id)}
                          style={{
                            padding: "0.5rem 1rem",
                            fontSize: "0.8rem",
                            fontWeight: "600",
                            background: "#f0fdf4",
                            color: "#16a34a",
                            border: "1px solid #bbf7d0",
                            borderRadius: "8px",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem"
                          }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>
                          Ver Evidencia
                        </button>
                      ) : (
                        <span style={{ fontSize: "0.8rem", color: "#94a3b8", fontStyle: "italic" }}>Sin evidencia</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <Pagination
            currentPage={currentPage}
            totalItems={logs.length}
            itemsPerPage={itemsPerPage}
            onPageChange={setCurrentPage}
          />
        </>
      )}
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

export default UserAccessLogs;
