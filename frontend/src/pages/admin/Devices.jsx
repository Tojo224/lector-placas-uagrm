import { useEffect, useState, useCallback } from "react";
import Loader from "../../components/Loader";
import ConfirmModal from "../../components/ConfirmModal";
import SearchBar from "../../components/SearchBar";
import {
  getDevices,
  createDevice,
  updateDevice,
  deleteDevice,
  getDeviceTypes,
  createDeviceType,
  updateDeviceType,
  deleteDeviceType
} from "../../api/devices";
import { useAuth } from "../../hooks/useAuth";

function Devices() {
  const { user } = useAuth();
  const isAdmin = user?.rol === "ADMINISTRADOR";
  const isStaff = user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR";

  const [activeTab, setActiveTab] = useState("devices"); // "devices" | "types"

  // Datos
  const [devices, setDevices] = useState([]);
  const [types, setTypes] = useState([]);
  const [devicesSearchQuery, setDevicesSearchQuery] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Formularios Modales
  const [creatingDevice, setCreatingDevice] = useState(null); // { nombre: "", ubicacion: "", tipo_dispositivo_id: "", esta_activo: true }
  const [editingDevice, setEditingDevice] = useState(null); // { id, nombre: "", ubicacion: "", tipo_dispositivo_id: "", esta_activo: true }
  const [viewingDevice, setViewingDevice] = useState(null);

  const [creatingType, setCreatingType] = useState(null); // { nombre: "" }
  const [editingType, setEditingType] = useState(null); // { id, nombre: "" }

  const [confirmConfig, setConfirmConfig] = useState({
    isOpen: false,
    title: "",
    message: "",
    confirmColor: "var(--color-primary)",
    onConfirm: null
  });

  const loadData = useCallback(async (isManual = false) => {
    try {
      if (isManual) setIsRefreshing(true);
      else setLoading(true);
      setError("");
      setSuccess("");

      const [devicesData, typesData] = await Promise.all([
        getDevices(),
        getDeviceTypes()
      ]);

      setDevices(devicesData || []);
      setTypes(typesData || []);
    } catch (err) {
      setError("No se pudo cargar la información de dispositivos.");
      console.error(err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (user?.id) {
      loadData();
    }
  }, [user, loadData]);

  // ── ACCIONES: DISPOSITIVOS ────────────────────────────────────────
  const handleOpenCreateDevice = () => {
    setCreatingDevice({
      nombre: "",
      ubicacion: "",
      tipo_dispositivo_id: types[0]?.id || "",
      esta_activo: true,
      webhook_url: ""
    });
    setError("");
    setSuccess("");
  };

  const handleCreateDeviceSubmit = (e) => {
    e.preventDefault();
    if (!creatingDevice.tipo_dispositivo_id) {
      setError("Por favor, asegúrate de que existan tipos de dispositivo antes de registrar.");
      return;
    }
    setError("");

    setConfirmConfig({
      isOpen: true,
      title: "Registrar Dispositivo",
      message: `¿Confirmas el registro del dispositivo "${creatingDevice.nombre}"?`,
      confirmColor: "var(--color-primary)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await createDevice(creatingDevice);
          setSuccess(`Dispositivo "${creatingDevice.nombre}" registrado con éxito.`);
          setCreatingDevice(null);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo registrar el dispositivo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  const handleOpenEditDevice = (d) => {
    setEditingDevice({
      id: d.id,
      nombre: d.nombre,
      ubicacion: d.ubicacion,
      tipo_dispositivo_id: d.tipo_dispositivo_id,
      esta_activo: d.esta_activo,
      webhook_url: d.webhook_url || ""
    });
    setError("");
    setSuccess("");
  };

  const handleEditDeviceSubmit = (e) => {
    e.preventDefault();
    if (!editingDevice?.id) return;

    setConfirmConfig({
      isOpen: true,
      title: "Guardar Cambios",
      message: `¿Estás seguro de que deseas guardar los cambios para el dispositivo "${editingDevice.nombre}"?`,
      confirmColor: "var(--color-primary)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await updateDevice(editingDevice.id, editingDevice);
          setSuccess(`Dispositivo "${editingDevice.nombre}" actualizado con éxito.`);
          setEditingDevice(null);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo actualizar el dispositivo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  const handleDeleteDevice = (d) => {
    setConfirmConfig({
      isOpen: true,
      title: "Eliminar Dispositivo",
      message: `¿Estás seguro de que deseas eliminar permanentemente el dispositivo "${d.nombre}"? Esta acción es irreversible.`,
      confirmColor: "#e11d48",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteDevice(d.id);
          setSuccess(`Dispositivo "${d.nombre}" eliminado con éxito.`);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo eliminar el dispositivo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  // ── ACCIONES: TIPOS DE DISPOSITIVO ──────────────────────────────
  const handleCreateTypeSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await createDeviceType({ nombre: creatingType.nombre });
      setSuccess(`Tipo "${creatingType.nombre}" registrado con éxito.`);
      setCreatingType(null);
      loadData();
    } catch (err) {
      setError(err.message || "No se pudo registrar el tipo.");
    } finally {
      setSaving(false);
    }
  };

  const handleEditTypeSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await updateDeviceType(editingType.id, { nombre: editingType.nombre });
      setSuccess(`Tipo de dispositivo actualizado con éxito.`);
      setEditingType(null);
      loadData();
    } catch (err) {
      setError(err.message || "No se pudo actualizar el tipo.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteType = (t) => {
    setConfirmConfig({
      isOpen: true,
      title: "Eliminar Tipo",
      message: `¿Estás seguro de que deseas eliminar el tipo de dispositivo "${t.nombre}"? Esto afectará a los dispositivos asociados.`,
      confirmColor: "#e11d48",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteDeviceType(t.id);
          setSuccess(`Tipo "${t.nombre}" eliminado.`);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo eliminar el tipo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  if (loading) {
    return <Loader label="Cargando dispositivos..." />;
  }

  return (
    <section className="page-stack">
      {/* Cabecera Principal */}
      <div className="hero card">
        <p className="eyebrow">Administración</p>
        <h2>Gestión de Dispositivos e Interfaces</h2>
        <p className="muted-text">
          Registra cámaras, barreras automáticas u otros dispositivos autorizados en los accesos del campus.
        </p>
      </div>

      {/* Selector de pestañas para administradores */}
      {isAdmin && (
        <div style={{ display: "flex", gap: "1rem", borderBottom: "2px solid rgba(21, 62, 117, 0.1)", paddingBottom: "0.5rem", marginBottom: "1.5rem" }}>
          <button
            type="button"
            onClick={() => { setActiveTab("devices"); setError(""); setSuccess(""); }}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === "devices" ? "3px solid var(--color-primary)" : "none",
              color: activeTab === "devices" ? "var(--color-primary)" : "#666",
              padding: "0.5rem 1rem",
              fontWeight: "bold",
              cursor: "pointer"
            }}
          >
            Dispositivos
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab("types"); setError(""); setSuccess(""); }}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === "types" ? "3px solid var(--color-primary)" : "none",
              color: activeTab === "types" ? "var(--color-primary)" : "#666",
              padding: "0.5rem 1rem",
              fontWeight: "bold",
              cursor: "pointer"
            }}
          >
            Gestionar Tipos de Dispositivo
          </button>
        </div>
      )}

      {success && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}><p style={{ color: "green", fontWeight: "bold", background: "#e6ffe6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid green", margin: 0 }}>{success}</p></div>}
      {error && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}><p className="error-text" style={{ background: "#ffe6e6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid red", display: "inline-block", margin: 0 }}>{error}</p></div>}

      {/* ── PESTAÑA: DISPOSITIVOS ────────────────────────────────────── */}
      {activeTab === "devices" && (
        <>
          <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
            <div>
              <p className="eyebrow">Listado de Dispositivos</p>
              <h3>Cámaras y Actuadores en Red</h3>
            </div>
            {isAdmin && (
              <button type="button" onClick={handleOpenCreateDevice} style={{ padding: "0.6rem 1.2rem" }}>
                Agregar Dispositivo
              </button>
            )}
          </div>

          <SearchBar
            searchQuery={devicesSearchQuery}
            setSearchQuery={setDevicesSearchQuery}
            placeholder="Buscar dispositivos por nombre, ubicación o tipo..."
            onRefresh={loadData}
            isRefreshing={isRefreshing}
            refreshTitle="Refrescar"
          />

          {!devices.filter(d => {
            const query = devicesSearchQuery.toLowerCase();
            const name = d.nombre?.toLowerCase() || "";
            const location = d.ubicacion?.toLowerCase() || "";
            const typeName = d.tipo?.nombre?.toLowerCase() || "";
            return name.includes(query) || location.includes(query) || typeName.includes(query);
          }).length && (
            <div className="card">
              <p className="muted-text text-center">No se encontraron dispositivos con ese filtro.</p>
            </div>
          )}

          {devices.filter(d => {
            const query = devicesSearchQuery.toLowerCase();
            const name = d.nombre?.toLowerCase() || "";
            const location = d.ubicacion?.toLowerCase() || "";
            const typeName = d.tipo?.nombre?.toLowerCase() || "";
            return name.includes(query) || location.includes(query) || typeName.includes(query);
          }).length > 0 && (
            <div className="card" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
                    <th style={{ padding: "1rem" }}>Nombre</th>
                    <th style={{ padding: "1rem" }}>Ubicación</th>
                    <th style={{ padding: "1rem" }}>Tipo</th>
                    <th style={{ padding: "1rem" }}>Estado</th>
                    {isStaff && <th style={{ padding: "1rem", textAlign: "right" }}>Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {devices
                    .filter(d => {
                      const query = devicesSearchQuery.toLowerCase();
                      const name = d.nombre?.toLowerCase() || "";
                      const location = d.ubicacion?.toLowerCase() || "";
                      const typeName = d.tipo?.nombre?.toLowerCase() || "";
                      return name.includes(query) || location.includes(query) || typeName.includes(query);
                    })
                    .map((d) => (
                      <tr key={d.id} style={{ borderBottom: "1px solid rgba(21, 62, 117, 0.05)" }}>
                        <td style={{ padding: "1rem", fontWeight: "bold" }}>
                          {d.nombre}
                        </td>
                        <td style={{ padding: "1rem" }}>
                          {d.ubicacion}
                        </td>
                      <td style={{ padding: "1rem" }}>
                        {d.tipo?.nombre || "N/A"}
                      </td>
                      <td style={{ padding: "1rem" }}>
                        <span style={{
                          padding: "0.25rem 0.5rem",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                          fontWeight: "bold",
                          background: d.esta_activo ? "#e6ffe6" : "#ffe6e6",
                          color: d.esta_activo ? "green" : "red",
                          border: `1px solid ${d.esta_activo ? "green" : "red"}`
                        }}>
                          {d.esta_activo ? "Activo" : "Inactivo"}
                        </span>
                      </td>
                      {isStaff && (
                        <td style={{ padding: "1rem", textAlign: "right", display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            onClick={() => setViewingDevice(d)}
                            title="Ver detalles"
                            style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "#0f766e", color: "white", border: "none", cursor: "pointer" }}
                          >
                            <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>visibility</span>
                          </button>
                          {isAdmin && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleOpenEditDevice(d)}
                                title="Editar dispositivo"
                                style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-primary)", color: "white", border: "none", cursor: "pointer" }}
                              >
                                <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>edit</span>
                              </button>
                              <button
                                type="button"
                                className="danger-button"
                                onClick={() => handleDeleteDevice(d)}
                                title="Eliminar dispositivo"
                                style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "#e11d48", color: "white", border: "none", cursor: "pointer" }}
                              >
                                <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>delete</span>
                              </button>
                            </>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── PESTAÑA: TIPOS DE DISPOSITIVOS ────────────────────────────── */}
      {activeTab === "types" && isAdmin && (
        <>
          <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
            <div>
              <p className="eyebrow">Catálogos</p>
              <h3>Clases de Dispositivo</h3>
            </div>
            <button type="button" onClick={() => setCreatingType({ nombre: "" })} style={{ padding: "0.6rem 1.2rem" }}>
              Agregar Nueva Clase
            </button>
          </div>

          {!types.length && (
            <div className="card">
              <p className="muted-text text-center">No hay clases de dispositivos registradas.</p>
            </div>
          )}

          {types.length > 0 && (
            <div className="card" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
                    <th style={{ padding: "1rem" }}>Nombre de la Clase</th>
                    <th style={{ padding: "1rem" }}>ID</th>
                    <th style={{ padding: "1rem", textAlign: "right" }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {types.map((t) => (
                    <tr key={t.id} style={{ borderBottom: "1px solid rgba(21, 62, 117, 0.05)" }}>
                      <td style={{ padding: "1rem", fontWeight: "bold" }}>
                        {t.nombre}
                      </td>
                      <td style={{ padding: "1rem", fontFamily: "monospace", fontSize: "0.85rem", color: "#666" }}>
                        {t.id}
                      </td>
                      <td style={{ padding: "1rem", textAlign: "right", display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          onClick={() => setEditingType({ id: t.id, nombre: t.nombre })}
                          title="Editar tipo"
                          style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-primary)", color: "white", border: "none", cursor: "pointer" }}
                        >
                          <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>edit</span>
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleDeleteType(t)}
                          title="Eliminar tipo"
                          style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "#e11d48", color: "white", border: "none", cursor: "pointer" }}
                        >
                          <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>delete</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── MODALES: DISPOSITIVOS ────────────────────────────────────── */}
      {creatingDevice && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleCreateDeviceSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Administración</p>
                <h2>Registrar nuevo dispositivo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setCreatingDevice(null)}>
                Cerrar
              </button>
            </div>

            <div className="form-block">
              <h4>Datos de Red e Identidad</h4>
              <div className="details-grid">
                <label className="field-group">
                  <span>Nombre Identificador</span>
                  <input
                    type="text"
                    placeholder="Ej. Cámara Entrada Principal, Barrera 1"
                    value={creatingDevice.nombre}
                    onChange={(e) => setCreatingDevice(prev => ({ ...prev, nombre: e.target.value }))}
                    required
                  />
                </label>

                <label className="field-group">
                  <span>Ubicación Física</span>
                  <input
                    type="text"
                    placeholder="Ej. Puerta de Ingreso Norte"
                    value={creatingDevice.ubicacion}
                    onChange={(e) => setCreatingDevice(prev => ({ ...prev, ubicacion: e.target.value }))}
                    required
                  />
                </label>

                <label className="field-group">
                  <span>Clase de Dispositivo</span>
                  {types.length > 0 ? (
                    <select
                      value={creatingDevice.tipo_dispositivo_id}
                      onChange={(e) => setCreatingDevice(prev => ({ ...prev, tipo_dispositivo_id: e.target.value }))}
                      required
                    >
                      {types.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.nombre}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", color: "#e11d48", background: "#fef2f2", border: "1px solid #fee2e2", padding: "0.5rem 0.8rem", borderRadius: "6px", fontSize: "0.85rem", marginTop: "5px" }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: "2px" }}><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      <span>No hay clases de dispositivos registradas. Agrégalas en la otra pestaña primero.</span>
                    </div>
                  )}
                </label>

                <label className="field-group" style={{ flexDirection: "row", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
                  <input
                    type="checkbox"
                    checked={creatingDevice.esta_activo}
                    onChange={(e) => setCreatingDevice(prev => ({ ...prev, esta_activo: e.target.checked }))}
                    style={{ width: "auto" }}
                  />
                  <span>Dispositivo habilitado y transmitiendo</span>
                </label>

                <label className="field-group" style={{ gridColumn: "1 / -1" }}>
                  <span>🔔 URL de Webhook — Barrera / Actuador</span>
                  <input
                    type="url"
                    placeholder="http://localhost:8000/api/v1/barrier/trigger"
                    value={creatingDevice.webhook_url || ""}
                    onChange={(e) => setCreatingDevice(prev => ({ ...prev, webhook_url: e.target.value }))}
                  />
                  <small style={{ color: "#64748b", fontSize: "0.78rem", marginTop: "0.25rem", display: "block" }}>
                    Opcional. Cuando se autorice un vehículo, el sistema enviará una señal POST a esta URL para abrir la barrera o actuador. Usa <strong>http://localhost:8000/api/v1/barrier/trigger</strong> para el simulador local.
                  </small>
                </label>
              </div>
            </div>

            <div className="modal-actions" style={{ marginTop: "1.5rem" }}>
              <button type="submit" disabled={saving || !types.length}>
                {saving ? "Registrando..." : "Registrar Dispositivo"}
              </button>
            </div>
          </form>
        </div>
      )}

      {editingDevice && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleEditDeviceSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Edición</p>
                <h2>Editar dispositivo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setEditingDevice(null)}>
                Cerrar
              </button>
            </div>

            <div className="form-block">
              <h4>Datos de Red e Identidad</h4>
              <div className="details-grid">
                <label className="field-group">
                  <span>Nombre Identificador</span>
                  <input
                    type="text"
                    value={editingDevice.nombre}
                    onChange={(e) => setEditingDevice(prev => ({ ...prev, nombre: e.target.value }))}
                    required
                  />
                </label>

                <label className="field-group">
                  <span>Ubicación Física</span>
                  <input
                    type="text"
                    value={editingDevice.ubicacion}
                    onChange={(e) => setEditingDevice(prev => ({ ...prev, ubicacion: e.target.value }))}
                    required
                  />
                </label>

                <label className="field-group">
                  <span>Clase de Dispositivo</span>
                  <select
                    value={editingDevice.tipo_dispositivo_id}
                    onChange={(e) => setEditingDevice(prev => ({ ...prev, tipo_dispositivo_id: e.target.value }))}
                    required
                  >
                    {types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.nombre}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field-group" style={{ flexDirection: "row", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
                  <input
                    type="checkbox"
                    checked={editingDevice.esta_activo}
                    onChange={(e) => setEditingDevice(prev => ({ ...prev, esta_activo: e.target.checked }))}
                    style={{ width: "auto" }}
                  />
                  <span>Dispositivo habilitado y transmitiendo</span>
                </label>

                <label className="field-group" style={{ gridColumn: "1 / -1" }}>
                  <span>🔔 URL de Webhook — Barrera / Actuador</span>
                  <input
                    type="url"
                    placeholder="http://localhost:8000/api/v1/barrier/trigger"
                    value={editingDevice.webhook_url || ""}
                    onChange={(e) => setEditingDevice(prev => ({ ...prev, webhook_url: e.target.value }))}
                  />
                  <small style={{ color: "#64748b", fontSize: "0.78rem", marginTop: "0.25rem", display: "block" }}>
                    Opcional. Señal automática al autorizar un vehículo. Usa <strong>http://localhost:8000/api/v1/barrier/trigger</strong> para el simulador local.
                  </small>
                </label>
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

      {/* ── MODALES: TIPOS DE DISPOSITIVOS ────────────────────────────── */}
      {creatingType && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleCreateTypeSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Catálogos</p>
                <h2>Agregar Nueva Clase de Dispositivo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setCreatingType(null)}>Cerrar</button>
            </div>
            <div className="form-block">
              <label className="field-group">
                <span>Nombre de la Clase</span>
                <input
                  type="text"
                  placeholder="Ej. Cámara Fija, Cámara Domo, Barrera Vehicular"
                  value={creatingType.nombre}
                  onChange={(e) => setCreatingType({ nombre: e.target.value })}
                  required
                />
              </label>
            </div>
            <div className="modal-actions" style={{ marginTop: "1rem" }}>
              <button type="submit" disabled={saving}>
                {saving ? "Registrando..." : "Registrar Clase"}
              </button>
            </div>
          </form>
        </div>
      )}

      {editingType && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleEditTypeSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Catálogos</p>
                <h2>Editar Clase de Dispositivo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setEditingType(null)}>Cerrar</button>
            </div>
            <div className="form-block">
              <label className="field-group">
                <span>Nombre de la Clase</span>
                <input
                  type="text"
                  value={editingType.nombre}
                  onChange={(e) => setEditingType(prev => ({ ...prev, nombre: e.target.value }))}
                  required
                />
              </label>
            </div>
            <div className="modal-actions" style={{ marginTop: "1rem" }}>
              <button type="submit" disabled={saving}>
                {saving ? "Guardando..." : "Guardar Cambios"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal de Detalles de Dispositivo */}
      {viewingDevice && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large" style={{ maxWidth: "720px" }}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Detalle</p>
                <h2>Información del dispositivo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setViewingDevice(null)}>
                Cerrar
              </button>
            </div>

            <div className="form-block" style={{ padding: "0.5rem 0" }}>
              <div className="details-grid" style={{ display: "grid", gap: "0.8rem" }}>
                <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.9rem 1rem", gridColumn: "1 / -1" }}>
                  <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Nombre Identificador</p>
                  <p style={{ margin: 0, fontSize: "1.1rem", fontWeight: "700" }}>{viewingDevice.nombre}</p>
                </div>
                
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.8rem", gridColumn: "1 / -1" }}>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Ubicación Física</p>
                    <p style={{ margin: 0, fontWeight: "600" }}>{viewingDevice.ubicacion}</p>
                  </div>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Clase / Tipo</p>
                    <p style={{ margin: 0, fontWeight: "600" }}>{viewingDevice.tipo?.nombre || "N/A"}</p>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.8rem", gridColumn: "1 / -1" }}>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Estado</p>
                    <span style={{
                      display: "inline-block",
                      marginTop: "0.25rem",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      fontWeight: "bold",
                      background: viewingDevice.esta_activo ? "#e6ffe6" : "#ffe6e6",
                      color: viewingDevice.esta_activo ? "green" : "red",
                      border: `1px solid ${viewingDevice.esta_activo ? "green" : "red"}`
                    }}>
                      {viewingDevice.esta_activo ? "Habilitado y transmitiendo" : "Inactivo"}
                    </span>
                  </div>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Identificador ID</p>
                    <p style={{ margin: 0, fontFamily: "monospace", fontSize: "0.85rem", wordBreak: "break-all" }}>{viewingDevice.id}</p>
                  </div>
                </div>

                <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.9rem 1rem", gridColumn: "1 / -1" }}>
                  <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>URL de Webhook (Barrera / Actuador)</p>
                  <p style={{ margin: 0, fontFamily: "monospace", fontSize: "0.85rem", wordBreak: "break-all" }}>
                    {viewingDevice.webhook_url || "No configurada"}
                  </p>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.8rem", gridColumn: "1 / -1" }}>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Fecha de Registro</p>
                    <p style={{ margin: 0, fontWeight: "600", fontSize: "0.85rem" }}>
                      {viewingDevice.creado_el 
                        ? new Date(viewingDevice.creado_el).toLocaleString("es-BO", { timeZone: "America/La_Paz", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
                        : "No disponible"}
                    </p>
                  </div>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Última Actualización</p>
                    <p style={{ margin: 0, fontWeight: "600", fontSize: "0.85rem" }}>
                      {viewingDevice.actualizado_el 
                        ? new Date(viewingDevice.actualizado_el).toLocaleString("es-BO", { timeZone: "America/La_Paz", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
                        : "No disponible"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Confirmación */}
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

export default Devices;
