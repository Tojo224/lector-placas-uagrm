import React, { useEffect } from "react";

export default function PlateNotFoundModal({
  manualPlate,
  setActiveModal,
  setManualPlate,
  activeTab,
  startCamera,
  requestSent = false,
  reason = ""
}) {
  const closeTimeout = requestSent ? 8000 : 5000;

  useEffect(() => {
    const timer = setTimeout(() => {
      setActiveModal(null);
      setManualPlate("");
    }, closeTimeout);

    return () => clearTimeout(timer);
  }, [setActiveModal, setManualPlate, closeTimeout]);

  return (
    <div className="modal-backdrop">
      <div className="modal-card" style={{ maxWidth: "420px", textAlign: "center" }}>
        <div style={{ padding: "2.5rem 1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "1.5rem" }}>
            {requestSent ? (
              <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
            ) : (
              <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
              </svg>
            )}
          </div>
          <p className="eyebrow" style={{
            color: requestSent ? "#d97706" : "#dc2626",
            fontWeight: "bold",
            textTransform: "uppercase",
            letterSpacing: "1px",
            marginBottom: "1rem"
          }}>
            {requestSent ? "Revisión requerida" : "Acceso denegado"}
          </p>
          <h2 style={{ marginBottom: "1rem", fontSize: "1.6rem", color: "#153e75" }}>
            {requestSent
              ? "Vehículo no registrado — solicitud enviada"
              : "Placa no registrada"}
          </h2>
          {manualPlate && (
            <p style={{ fontFamily: "monospace", fontSize: "1.6rem", fontWeight: "bold", color: "#153e75", margin: 0 }}>
              {manualPlate}
            </p>
          )}
          {requestSent && (
            <p className="muted-text" style={{ marginTop: "0.75rem", fontSize: "0.9rem", lineHeight: "1.5" }}>
              La imagen fue enviada al servidor central para revisión por un administrador.
              La solicitud quedará pendiente hasta su aprobación.
            </p>
          )}
          {!requestSent && reason && (
            <p className="muted-text" style={{ marginTop: "0.75rem" }}>{reason}</p>
          )}
        </div>
      </div>
    </div>
  );
}
