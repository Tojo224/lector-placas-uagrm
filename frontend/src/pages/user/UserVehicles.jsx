import { useEffect, useState, useCallback } from "react";
import Loader from "../../components/Loader";
import ConfirmModal from "../../components/ConfirmModal";
import {
  getVehicles,
  createVehicle,
  updateVehicle,
  deleteVehicle,
  getBrands,
  getVehicleTypes,
  uploadVehiclePhoto,
  deleteVehiclePhoto,
  getMediaUrl
} from "../../api/plates";
import { useAuth } from "../../hooks/useAuth";
import { formatPlate, validatePlateForm } from "../../utils/formatters";
import Pagination from "../../components/Pagination";

// Componente de Tarjeta de Vehículo Premium
function VehicleCard({ vehicle, onEdit, onDelete }) {
  const [url, setUrl] = useState("");
  const [loadingPhoto, setLoadingPhoto] = useState(false);

  useEffect(() => {
    if (!vehicle.foto_id) {
      setUrl("");
      return;
    }
    setLoadingPhoto(true);
    getMediaUrl(vehicle.foto_id)
      .then((res) => {
        setUrl(res.url);
      })
      .catch((err) => {
        console.error("Error cargando foto de tarjeta:", err);
      })
      .finally(() => {
        setLoadingPhoto(false);
      });
  }, [vehicle.foto_id]);

  return (
    <div 
      className="card"
      style={{
        display: "flex",
        flexDirection: "column",
        borderRadius: "16px",
        overflow: "hidden",
        border: "1px solid rgba(21, 62, 117, 0.08)",
        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)",
        transition: "transform 0.2s, box-shadow 0.2s",
        background: "#ffffff",
        height: "100%"
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-4px)";
        e.currentTarget.style.boxShadow = "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)";
      }}
    >
      {/* Contenedor de la Foto */}
      <div 
        style={{ 
          width: "100%", 
          height: "180px", 
          position: "relative", 
          overflow: "hidden",
          background: "#f1f5f9",
          display: "flex",
          alignItems: "center",
          justifyContent: "center"
        }}
      >
        {loadingPhoto ? (
          <span style={{ fontSize: "0.9rem", color: "#64748b" }}>Cargando foto...</span>
        ) : url ? (
          <img 
            src={url} 
            alt={`Vehículo ${vehicle.placa}`}
            style={{ 
              width: "100%", 
              height: "100%", 
              objectFit: "cover",
              cursor: "pointer"
            }}
            onClick={() => window.open(url, "_blank")}
            title="Ver foto en tamaño completo"
          />
        ) : (
          <div 
            style={{ 
              width: "100%", 
              height: "100%", 
              background: "linear-gradient(135deg, #153e75 0%, #1e40af 100%)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              color: "rgba(255, 255, 255, 0.9)",
              padding: "1rem",
              textAlign: "center"
            }}
          >
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: "0.5rem", color: "rgba(255, 255, 255, 0.8)" }}><path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/></svg>
            <span style={{ fontSize: "0.85rem", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.25rem" }}>Sin foto</span>
            <p style={{ fontSize: "0.72rem", color: "rgba(255, 255, 255, 0.75)", margin: 0, lineHeight: "1.3" }}>
              Sube una foto del vehículo para facilitar su validación visual en los puntos de control del campus.
            </p>
          </div>
        )}
      </div>

      {/* Contenido de la Tarjeta */}
      <div style={{ padding: "1.25rem", flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
        <div>
          {/* Faux Placa de Vehículo Boliviana */}
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "1rem" }}>
            <div 
              style={{
                background: "#ffffff",
                border: "2.5px solid #1e3a8a",
                borderRadius: "6px",
                padding: "2px",
                width: "160px",
                boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                userSelect: "none"
              }}
            >
              {/* Encabezado azul de la placa */}
              <div 
                style={{ 
                  background: "#1e3a8a", 
                  color: "#ffffff", 
                  width: "100%", 
                  fontSize: "0.6rem", 
                  textAlign: "center", 
                  fontWeight: "bold", 
                  letterSpacing: "0.15em",
                  padding: "1px 0",
                  borderRadius: "2px 2px 0 0"
                }}
              >
                BOLIVIA
              </div>
              {/* Texto de la placa */}
              <span 
                style={{ 
                  fontFamily: "monospace", 
                  fontSize: "1.4rem", 
                  fontWeight: "900", 
                  color: "#1e293b",
                  letterSpacing: "2px",
                  lineHeight: "1.8rem"
                }}
              >
                {vehicle.placa}
              </span>
            </div>
          </div>

          {/* Información del Vehículo */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.9rem", color: "#475569", marginBottom: "1.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed #e2e8f0", paddingBottom: "0.3rem" }}>
              <span style={{ color: "#64748b" }}>Marca</span>
              <strong style={{ color: "#1e293b" }}>{vehicle.marca?.nombre || "N/A"}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed #e2e8f0", paddingBottom: "0.3rem" }}>
              <span style={{ color: "#64748b" }}>Tipo</span>
              <span style={{ color: "#1e293b", fontWeight: "500" }}>{vehicle.tipo?.nombre || "N/A"}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", paddingBottom: "0.3rem" }}>
              <span style={{ color: "#64748b" }}>Color</span>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span style={{ color: "#1e293b", fontWeight: "500" }}>{vehicle.color || "N/A"}</span>
                {vehicle.color_hex && (
                  <span 
                    title={vehicle.color_hex}
                    style={{ 
                      display: "inline-block",
                      width: "12px", 
                      height: "12px", 
                      borderRadius: "50%", 
                      backgroundColor: vehicle.color_hex,
                      border: "1px solid #cbd5e1"
                    }} 
                  />
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Acciones */}
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "auto" }}>
          <button
            type="button"
            onClick={() => onEdit(vehicle)}
            style={{ 
              flex: 1, 
              padding: "0.6rem", 
              fontSize: "0.85rem", 
              fontWeight: "600",
              background: "#eff6ff", 
              color: "#1e40af", 
              border: "1px solid #bfdbfe",
              borderRadius: "8px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.3rem"
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
            Editar
          </button>
          <button
            type="button"
            className="danger-button"
            onClick={() => onDelete(vehicle)}
            style={{ 
              flex: 1, 
              padding: "0.6rem", 
              fontSize: "0.85rem", 
              fontWeight: "600",
              borderRadius: "8px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.3rem"
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
            Eliminar
          </button>
        </div>
      </div>
    </div>
  );
}

function UserVehicles() {
  const { user } = useAuth();

  // Datos
  const [vehicles, setVehicles] = useState([]);
  const [brands, setBrands] = useState([]);
  const [types, setTypes] = useState([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 6; // Ajustado a 6 para calzar perfecto con grids de 3 o 2 columnas

  // Formularios Modales
  const [creatingVehicle, setCreatingVehicle] = useState(null);
  const [editingVehicle, setEditingVehicle] = useState(null);
  const [editingVehiclePhotoUrl, setEditingVehiclePhotoUrl] = useState("");

  const [confirmConfig, setConfirmConfig] = useState({
    isOpen: false,
    title: "",
    message: "",
    confirmColor: "var(--color-primary)",
    onConfirm: null
  });

  const loadData = useCallback(async () => {
    if (!user?.id) return;
    try {
      setLoading(true);
      setError("");
      setSuccess("");

      const [vehiclesData, brandsData, typesData] = await Promise.all([
        getVehicles(user.id),
        getBrands(),
        getVehicleTypes()
      ]);

      setVehicles(vehiclesData || []);
      setBrands(brandsData || []);
      setTypes(typesData || []);
    } catch (err) {
      setError("No se pudo cargar la información de tus vehículos.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Paginación
  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentVehicles = vehicles.slice(indexOfFirstItem, indexOfLastItem);

  const handleOpenCreateVehicle = () => {
    if (!brands.length || !types.length) {
      setError("No hay marcas o tipos de vehículos registrados en el sistema.");
      return;
    }
    setCreatingVehicle({
      placa: "",
      color: "",
      color_hex: "",
      marca_id: brands[0]?.id || "",
      tipo_vehiculo_id: types[0]?.id || "",
      propietario_usuario_id: user?.id,
      photoFile: null
    });
    setError("");
    setSuccess("");
  };

  const handleCreateVehicleSubmit = (e) => {
    e.preventDefault();
    setError("");

    const plateVal = formatPlate(creatingVehicle.placa);

    setConfirmConfig({
      isOpen: true,
      title: "Registrar Vehículo",
      message: `¿Confirmas el registro del vehículo con placa ${plateVal}?`,
      confirmColor: "var(--color-primary)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          const newVehicle = await createVehicle({
            placa: plateVal,
            color: creatingVehicle.color,
            color_hex: creatingVehicle.color_hex || null,
            marca_id: creatingVehicle.marca_id,
            tipo_vehiculo_id: creatingVehicle.tipo_vehiculo_id,
            propietario_usuario_id: user?.id
          });
          if (creatingVehicle.photoFile) {
            await uploadVehiclePhoto(newVehicle.id, creatingVehicle.photoFile);
          }
          setSuccess(`Vehículo ${plateVal} registrado con éxito.`);
          setCreatingVehicle(null);
          loadData();
        } catch (err) {
          setError(err.response?.data?.detail || err.message || "No se pudo registrar el vehículo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  const handleOpenEditVehicle = async (v) => {
    setEditingVehicle({
      id: v.id,
      placa: v.placa,
      color: v.color,
      color_hex: v.color_hex || "",
      marca_id: v.marca_id,
      tipo_vehiculo_id: v.tipo_vehiculo_id,
      propietario_usuario_id: user?.id,
      foto_id: v.foto_id,
      photoFile: null
    });
    setEditingVehiclePhotoUrl("");
    setError("");
    setSuccess("");

    if (v.foto_id) {
      try {
        const result = await getMediaUrl(v.foto_id);
        setEditingVehiclePhotoUrl(result.url);
      } catch (err) {
        console.error("No se pudo cargar la foto del vehículo:", err);
      }
    }
  };

  const handleDeleteVehiclePhoto = (vehicleId) => {
    setConfirmConfig({
      isOpen: true,
      title: "Eliminar Foto",
      message: "¿Estás seguro de que deseas eliminar la foto de este vehículo?",
      confirmColor: "var(--color-danger, #ef4444)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteVehiclePhoto(vehicleId);
          setEditingVehiclePhotoUrl("");
          setEditingVehicle(current => ({ ...current, foto_id: null }));
          setSuccess("Foto del vehículo eliminada.");
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo eliminar la foto.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  const handleEditVehicleSubmit = (e) => {
    e.preventDefault();
    if (!editingVehicle?.id) return;

    setError("");
    const plateVal = formatPlate(editingVehicle.placa);

    setConfirmConfig({
      isOpen: true,
      title: "Guardar Cambios",
      message: `¿Confirmas las modificaciones en el vehículo con placa ${plateVal}?`,
      confirmColor: "var(--color-primary)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await updateVehicle(editingVehicle.id, {
            placa: plateVal,
            color: editingVehicle.color,
            color_hex: editingVehicle.color_hex || null,
            marca_id: editingVehicle.marca_id,
            tipo_vehiculo_id: editingVehicle.tipo_vehiculo_id,
            propietario_usuario_id: user?.id
          });
          if (editingVehicle.photoFile) {
            await uploadVehiclePhoto(editingVehicle.id, editingVehicle.photoFile);
          }
          setSuccess(`Vehículo ${plateVal} actualizado.`);
          setEditingVehicle(null);
          loadData();
        } catch (err) {
          setError(err.response?.data?.detail || err.message || "No se pudo actualizar el vehículo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  const handleDeleteVehicle = (v) => {
    setConfirmConfig({
      isOpen: true,
      title: "Eliminar Vehículo",
      message: `¿Estás seguro de que deseas eliminar el vehículo con placa ${v.placa}? Esta acción no se puede deshacer.`,
      confirmColor: "var(--color-danger, #ef4444)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteVehicle(v.id);
          setSuccess(`Vehículo con placa ${v.placa} eliminado.`);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo eliminar el vehículo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  if (loading) {
    return <Loader label="Cargando tus vehículos..." />;
  }

  return (
    <section className="card page-stack" style={{ background: "transparent", border: "none", boxShadow: "none", padding: 0 }}>
      {success && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}><p style={{ color: "green", fontWeight: "bold", background: "#e6ffe6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid green", margin: 0 }}>{success}</p></div>}
      {error && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}><p className="error-text" style={{ background: "#ffe6e6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid red", display: "inline-block", margin: 0 }}>{error}</p></div>}

      <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1.5rem" }}>
        <div>
          <p className="eyebrow" style={{ textTransform: "uppercase", fontSize: "0.75rem", letterSpacing: "0.08em", fontWeight: "bold", color: "#64748b" }}>Mis Vehículos</p>
          <h2 style={{ fontSize: "1.75rem", fontWeight: "700", color: "#1e3a8a", margin: "0.25rem 0 0 0" }}>Vehículos registrados bajo mi cuenta</h2>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" className="ghost-button" onClick={loadData} style={{ padding: "0.6rem", display: "flex", alignItems: "center", justifyContent: "center", width: "40px", height: "40px", borderRadius: "8px" }} title="Refrescar lista">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.59-9.21l5.67-5.67"/></svg>
          </button>
        </div>
      </div>

      <div>
        {/* Grid de Tarjetas */}
        <div 
          style={{ 
            display: "grid", 
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", 
            gap: "1.5rem",
            marginBottom: "1.5rem"
          }}
        >
          {currentVehicles.map((v) => (
            <VehicleCard 
              key={v.id} 
              vehicle={v} 
              onEdit={handleOpenEditVehicle} 
              onDelete={handleDeleteVehicle} 
            />
          ))}

          {/* Tarjeta de Agregar Vehículo (+) */}
          <div
            onClick={handleOpenCreateVehicle}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "16px",
              border: "2.5px dashed #cbd5e1",
              background: "#f8fafc",
              cursor: "pointer",
              padding: "2rem",
              minHeight: "380px",
              transition: "all 0.2s ease",
              textAlign: "center",
              boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.02)"
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "#1e3a8a";
              e.currentTarget.style.background = "#eff6ff";
              e.currentTarget.style.transform = "translateY(-4px)";
              e.currentTarget.style.boxShadow = "0 10px 15px -3px rgba(0, 0, 0, 0.08)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "#cbd5e1";
              e.currentTarget.style.background = "#f8fafc";
              e.currentTarget.style.transform = "translateY(0)";
              e.currentTarget.style.boxShadow = "0 4px 6px -1px rgba(0, 0, 0, 0.02)";
            }}
          >
            <div 
              style={{
                width: "56px",
                height: "56px",
                borderRadius: "50%",
                background: "#ffffff",
                boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#1e3a8a",
                marginBottom: "1rem"
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </div>
            <span style={{ fontSize: "1.05rem", fontWeight: "700", color: "#1e3a8a" }}>Registrar Vehículo</span>
            <p style={{ fontSize: "0.8rem", color: "#64748b", marginTop: "0.5rem", maxWidth: "200px" }}>Añade un nuevo vehículo a tu cuenta universitaria</p>
          </div>
        </div>

        {vehicles.length > itemsPerPage && (
          <Pagination
            currentPage={currentPage}
            totalItems={vehicles.length}
            itemsPerPage={itemsPerPage}
            onPageChange={setCurrentPage}
          />
        )}
      </div>

      {/* Modal de Registro de Vehículo */}
      {creatingVehicle && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleCreateVehicleSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Registro</p>
                <h2>Registrar nuevo vehículo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setCreatingVehicle(null)}>
                Cerrar
              </button>
            </div>

            <div className="form-block">
              <h4>Datos del vehículo</h4>
              <div className="details-grid">
                <label className="field-group">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span>Placa</span>
                    <span style={{ fontSize: "0.75rem", color: "#64748b" }}>Obligatorio</span>
                  </div>
                  <input
                    type="text"
                    className={validatePlateForm(creatingVehicle.placa).className}
                    placeholder="Ej. 1234ABC o 1234ABC-BO"
                    value={creatingVehicle.placa}
                    onChange={(event) =>
                      setCreatingVehicle((current) => ({
                        ...current,
                        placa: event.target.value
                      }))
                    }
                    required
                  />
                  {validatePlateForm(creatingVehicle.placa).message && (
                    <span className={`field-hint ${validatePlateForm(creatingVehicle.placa).className === "field-valid" ? "valid" : "invalid"}`}>
                      {validatePlateForm(creatingVehicle.placa).message}
                    </span>
                  )}
                </label>

                <label className="field-group">
                  <span>Color</span>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <input
                      type="text"
                      placeholder="Ej. Blanco, Azul"
                      value={creatingVehicle.color}
                      onChange={(event) =>
                        setCreatingVehicle((current) => ({
                          ...current,
                          color: event.target.value
                        }))
                      }
                      required
                      style={{ flex: 1 }}
                    />
                    <input
                      type="color"
                      value={creatingVehicle.color_hex || "#cccccc"}
                      onChange={(event) =>
                        setCreatingVehicle((current) => ({
                          ...current,
                          color_hex: event.target.value
                        }))
                      }
                      style={{ 
                        width: "42px", 
                        height: "42px", 
                        padding: "2px", 
                        border: "1px solid var(--color-border)", 
                        borderRadius: "8px", 
                        cursor: "pointer",
                        flexShrink: 0
                      }}
                    />
                  </div>
                </label>

                <label className="field-group">
                  <span>Marca</span>
                  <select
                    value={creatingVehicle.marca_id}
                    onChange={(event) =>
                      setCreatingVehicle((current) => ({
                        ...current,
                        marca_id: event.target.value
                      }))
                    }
                    required
                  >
                    {brands.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.nombre}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field-group">
                  <span>Tipo de Vehículo</span>
                  <select
                    value={creatingVehicle.tipo_vehiculo_id}
                    onChange={(event) =>
                      setCreatingVehicle((current) => ({
                        ...current,
                        tipo_vehiculo_id: event.target.value
                      }))
                    }
                    required
                  >
                    {types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.nombre}
                      </option>
                    ))}
                  </select>
                </label>

                <div style={{ gridColumn: "1 / -1", display: "flex", gap: "0.5rem", alignItems: "center", background: "#f0f9ff", border: "1px solid #e0f2fe", padding: "0.6rem 1rem", borderRadius: "8px", fontSize: "0.85rem", color: "#0369a1" }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                  <span>El vehículo se registrará bajo tu propio nombre: <strong>{user?.nombre} {user?.apellido_paterno}</strong>.</span>
                </div>

                <label className="field-group">
                  <span>Foto privada del vehículo (Opcional)</span>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(event) =>
                      setCreatingVehicle((current) => ({
                        ...current,
                        photoFile: event.target.files?.[0] || null
                      }))
                    }
                  />
                </label>
              </div>
            </div>

            <div className="modal-actions" style={{ marginTop: "1.5rem" }}>
              <button type="submit" disabled={saving || !brands.length || !types.length}>
                {saving ? "Registrando..." : "Registrar Vehículo"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal de Edición de Vehículo */}
      {editingVehicle && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleEditVehicleSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Edición</p>
                <h2>Editar vehículo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setEditingVehicle(null)}>
                Cerrar
              </button>
            </div>

            <div className="form-block">
              <h4>Datos del vehículo</h4>
              <div className="details-grid">
                <label className="field-group">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span>Placa</span>
                    <span style={{ fontSize: "0.75rem", color: "#64748b" }}>Obligatorio</span>
                  </div>
                  <input
                    type="text"
                    className={validatePlateForm(editingVehicle.placa).className}
                    value={editingVehicle.placa}
                    onChange={(event) =>
                      setEditingVehicle((current) => ({
                        ...current,
                        placa: event.target.value
                      }))
                    }
                    required
                  />
                  {validatePlateForm(editingVehicle.placa).message && (
                    <span className={`field-hint ${validatePlateForm(editingVehicle.placa).className === "field-valid" ? "valid" : "invalid"}`}>
                      {validatePlateForm(editingVehicle.placa).message}
                    </span>
                  )}
                </label>

                <label className="field-group">
                  <span>Color</span>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <input
                      type="text"
                      value={editingVehicle.color}
                      onChange={(event) =>
                        setEditingVehicle((current) => ({
                          ...current,
                          color: event.target.value
                        }))
                      }
                      required
                      style={{ flex: 1 }}
                    />
                    <input
                      type="color"
                      value={editingVehicle.color_hex || "#cccccc"}
                      onChange={(event) =>
                        setEditingVehicle((current) => ({
                          ...current,
                          color_hex: event.target.value
                        }))
                      }
                      style={{ 
                        width: "42px", 
                        height: "42px", 
                        padding: "2px", 
                        border: "1px solid var(--color-border)", 
                        borderRadius: "8px", 
                        cursor: "pointer",
                        flexShrink: 0
                      }}
                    />
                  </div>
                </label>

                <label className="field-group">
                  <span>Marca</span>
                  <select
                    value={editingVehicle.marca_id}
                    onChange={(event) =>
                      setEditingVehicle((current) => ({
                        ...current,
                        marca_id: event.target.value
                      }))
                    }
                    required
                  >
                    {brands.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.nombre}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field-group">
                  <span>Tipo de Vehículo</span>
                  <select
                    value={editingVehicle.tipo_vehiculo_id}
                    onChange={(event) =>
                      setEditingVehicle((current) => ({
                        ...current,
                        tipo_vehiculo_id: event.target.value
                      }))
                    }
                    required
                  >
                    {types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.nombre}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="field-group" style={{ gridColumn: "1 / -1" }}>
                  <span>Foto privada del vehículo</span>
                  {editingVehiclePhotoUrl && (
                    <div style={{ marginBottom: "0.5rem" }}>
                      <img 
                        src={editingVehiclePhotoUrl} 
                        alt="Foto del vehículo" 
                        style={{ maxWidth: "200px", borderRadius: "8px", border: "1px solid #ddd", display: "block", marginBottom: "0.5rem" }} 
                      />
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => handleDeleteVehiclePhoto(editingVehicle.id)}
                        style={{ padding: "0.3rem 0.6rem", fontSize: "0.8rem" }}
                      >
                        Eliminar foto
                      </button>
                    </div>
                  )}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(event) =>
                      setEditingVehicle((current) => ({
                        ...current,
                        photoFile: event.target.files?.[0] || null
                      }))
                    }
                  />
                </div>
              </div>
            </div>

            <div className="modal-actions" style={{ marginTop: "1.5rem" }}>
              <button type="submit" disabled={saving}>
                {saving ? "Guardando..." : "Guardar Cambios"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal de Confirmación General */}
      <ConfirmModal
        isOpen={confirmConfig.isOpen}
        title={confirmConfig.title}
        message={confirmConfig.message}
        confirmColor={confirmConfig.confirmColor}
        onConfirm={confirmConfig.onConfirm}
        onCancel={() => setConfirmConfig({ ...confirmConfig, isOpen: false })}
      />
    </section>
  );
}

export default UserVehicles;
