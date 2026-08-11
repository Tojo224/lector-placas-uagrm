import { useEffect, useState, useCallback } from "react";
import Loader from "../../components/Loader";
import ConfirmModal from "../../components/ConfirmModal";
import {
  getVehicles,
  createVehicle,
  updateVehicle,
  deleteVehicle,
  getBrands,
  createBrand,
  updateBrand,
  deleteBrand,
  getVehicleTypes,
  createVehicleType,
  updateVehicleType,
  deleteVehicleType,
  uploadVehiclePhoto,
  deleteVehiclePhoto,
  getMediaUrl
} from "../../api/plates";
import { listUsers } from "../../api/auth";
import { useAuth } from "../../hooks/useAuth";
import { formatPlate, validatePlateForm } from "../../utils/formatters";
import Pagination from "../../components/Pagination";
import SearchBar from "../../components/SearchBar";

const CATALOG_COLORS = {
  "BLANCO": { r: 235, g: 235, b: 235, hex: "#EBEBEB" },
  "NEGRO": { r: 28, g: 28, b: 28, hex: "#1C1C1C" },
  "GRIS": { r: 105, g: 105, b: 105, hex: "#696969" },
  "PLATEADO": { r: 178, g: 178, b: 178, hex: "#B2B2B2" },
  "ROJO": { r: 190, g: 40, b: 40, hex: "#BE2828" },
  "AZUL": { r: 35, g: 85, b: 180, hex: "#2355B4" },
  "VERDE": { r: 65, g: 145, b: 65, hex: "#419141" },
  "AMARILLO": { r: 220, g: 205, b: 35, hex: "#DCCD23" },
  "MARRON": { r: 115, g: 75, b: 45, hex: "#734B2D" },
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

  Object.entries(CATALOG_COLORS).forEach(([name, data]) => {
    const dist = Math.sqrt(
      Math.pow(rgb.r - data.r, 2) +
      Math.pow(rgb.g - data.g, 2) +
      Math.pow(rgb.b - data.b, 2)
    );
    if (dist < minDistance) {
      minDistance = dist;
      closestName = name;
    }
  });

  return closestName;
}

function getColorHex(colorNameOrHex) {
  if (!colorNameOrHex) return "#cccccc";
  if (colorNameOrHex.startsWith("#")) return colorNameOrHex;
  const name = colorNameOrHex.toUpperCase().trim();
  return CATALOG_COLORS[name]?.hex || "#cccccc";
}

function VehicleTablePhoto({ fotoId }) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fotoId) {
      setUrl("");
      return;
    }
    setLoading(true);
    getMediaUrl(fotoId)
      .then((res) => {
        setUrl(res.url);
      })
      .catch((err) => {
        console.error("Error cargando url de la foto del vehiculo:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [fotoId]);

  if (!fotoId) {
    return <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>Sin foto</span>;
  }

  if (loading) {
    return <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>Cargando...</span>;
  }

  if (!url) {
    return <span style={{ color: "#ef4444", fontSize: "0.85rem" }}>Error</span>;
  }

  return (
    <img 
      src={url} 
      alt="Vehículo" 
      style={{ 
        width: "60px", 
        height: "40px", 
        objectFit: "cover", 
        borderRadius: "4px", 
        border: "1px solid #cbd5e1",
        cursor: "pointer",
        display: "block"
      }} 
      onClick={() => window.open(url, "_blank", "noopener,noreferrer")}
      title="Ver foto en tamaño completo"
    />
  );
}

function Vehicles() {
  const { user } = useAuth();
  const isAdmin = user?.rol === "ADMINISTRADOR";
  const isStaff = user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR";

  const [activeTab, setActiveTab] = useState("vehicles"); // "vehicles" | "brands" | "types"

  // Datos
  const [vehicles, setVehicles] = useState([]);
  const [brands, setBrands] = useState([]);
  const [types, setTypes] = useState([]);
  const [users, setUsers] = useState([]);
  const [vehiclePhotoUrls, setVehiclePhotoUrls] = useState({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [zoomedImage, setZoomedImage] = useState(null);

  const [filterType, setFilterType] = useState("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [vehiclesSearchQuery, setVehiclesSearchQuery] = useState("");
  const itemsPerPage = 10;

  const [creatingVehicle, setCreatingVehicle] = useState(null);
  const [editingVehicle, setEditingVehicle] = useState(null);
  const [viewingVehicle, setViewingVehicle] = useState(null);
  const [editingVehiclePhotoUrl, setEditingVehiclePhotoUrl] = useState("");

  const [creatingBrand, setCreatingBrand] = useState(null); // { nombre: "" }
  const [editingBrand, setEditingBrand] = useState(null); // { id, nombre: "" }

  const [creatingType, setCreatingType] = useState(null); // { nombre: "" }
  const [editingType, setEditingType] = useState(null); // { id, nombre: "" }

  const [confirmConfig, setConfirmConfig] = useState({
    isOpen: false,
    title: "",
    message: "",
    confirmColor: "var(--color-primary)",
    onConfirm: null
  });

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      setSuccess("");

      const [vehiclesData, brandsData, typesData, usersData] = await Promise.all([
        getVehicles(undefined),
        getBrands(),
        getVehicleTypes(),
        listUsers()
      ]);

      setVehicles(vehiclesData || []);
      setBrands(brandsData || []);
      setTypes(typesData || []);
      const normalUsers = (usersData || []).filter(u => u.rol === "USUARIO");
      setUsers(normalUsers);
    } catch (err) {
      setError("No se pudo cargar la información del sistema.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);


  useEffect(() => {
    if (user?.id) {
      loadData();
    }
  }, [user, loadData]);


  useEffect(() => {
    const photoIds = [...new Set(vehicles.map((vehicle) => vehicle.foto_id).filter(Boolean))];
    if (!photoIds.length) return;

    const missingPhotoIds = photoIds.filter((photoId) => !vehiclePhotoUrls[photoId]);
    if (!missingPhotoIds.length) return;

    let isMounted = true;
    Promise.all(
      missingPhotoIds.map(async (photoId) => {
        try {
          const response = await getMediaUrl(photoId);
          return [photoId, response?.url || ""];
        } catch {
          return [photoId, ""];
        }
      })
    ).then((entries) => {
      if (!isMounted) return;
      setVehiclePhotoUrls((current) => ({
        ...current,
        ...Object.fromEntries(entries)
      }));
    });

    return () => {
      isMounted = false;
    };
  }, [vehicles, vehiclePhotoUrls]);

  const handleOpenCreateVehicle = () => {
    setCreatingVehicle({
      placa: "",
      color: "",
      marca_id: brands[0]?.id || "",
      tipo_vehiculo_id: types[0]?.id || "",
      propietario_usuario_id: isStaff ? (users[0]?.id || "") : user?.id,
      photoFile: null
    });
    setError("");
    setSuccess("");
  };



  const handleCreateVehicleSubmit = (e) => {
    e.preventDefault();
    if (!creatingVehicle.marca_id || !creatingVehicle.tipo_vehiculo_id || !creatingVehicle.propietario_usuario_id) {
      setError("Por favor, asegúrate de que existan marcas, tipos y propietarios antes de registrar.");
      return;
    }
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
            marca_id: creatingVehicle.marca_id,
            tipo_vehiculo_id: creatingVehicle.tipo_vehiculo_id,
            propietario_usuario_id: creatingVehicle.propietario_usuario_id
          });
          if (creatingVehicle.photoFile) {
            await uploadVehiclePhoto(newVehicle.id, creatingVehicle.photoFile);
          }
          setSuccess(`Vehículo ${plateVal} registrado con éxito.`);
          setCreatingVehicle(null);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo registrar el vehículo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  const handleOpenVehicleDetails = (v) => {
    setViewingVehicle(v);
    setError("");
    setSuccess("");
  };

  const handleOpenEditVehicle = async (v) => {
    setEditingVehicle({
      id: v.id,
      placa: v.placa,
      color: v.color,
      marca_id: v.marca_id,
      tipo_vehiculo_id: v.tipo_vehiculo_id,
      propietario_usuario_id: v.propietario_usuario_id,
      foto_id: v.foto_id || null,
      photoFile: null
    });
    setEditingVehiclePhotoUrl("");
    setViewingVehicle(null);
    setError("");
    setSuccess("");

    if (v.foto_id) {
      try {
        const result = await getMediaUrl(v.foto_id);
        setEditingVehiclePhotoUrl(result.url);
      } catch (err) {
        console.error("No se pudo cargar la foto del vehiculo:", err);
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

    const plateVal = formatPlate(editingVehicle.placa);

    setConfirmConfig({
      isOpen: true,
      title: "Guardar Cambios",
      message: `¿Estás seguro de que deseas guardar los cambios para el vehículo con placa ${plateVal}?`,
      confirmColor: "var(--color-primary)",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await updateVehicle(editingVehicle.id, {
            placa: plateVal,
            color: editingVehicle.color,
            marca_id: editingVehicle.marca_id,
            tipo_vehiculo_id: editingVehicle.tipo_vehiculo_id,
            propietario_usuario_id: editingVehicle.propietario_usuario_id
          });
          if (editingVehicle.photoFile) {
            await uploadVehiclePhoto(editingVehicle.id, editingVehicle.photoFile);
          }
          setSuccess(`Vehículo ${plateVal} actualizado con éxito.`);
          setEditingVehicle(null);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo actualizar el vehículo.");
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
      message: `¿Estás seguro de que deseas eliminar permanentemente el vehículo con placa ${v.placa}? Esta acción es irreversible.`,
      confirmColor: "#e11d48",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteVehicle(v.id);
          setSuccess(`Vehículo con placa ${v.placa} eliminado con éxito.`);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo eliminar el vehículo.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  // ── ACCIONES: MARCAS (ADMIN ONLY) ───────────────────────────────
  const handleCreateBrandSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await createBrand({ nombre: creatingBrand.nombre });
      setSuccess(`Marca "${creatingBrand.nombre}" registrada con éxito.`);
      setCreatingBrand(null);
      loadData();
    } catch (err) {
      setError(err.message || "No se pudo registrar la marca.");
    } finally {
      setSaving(false);
    }
  };

  const handleEditBrandSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await updateBrand(editingBrand.id, { nombre: editingBrand.nombre });
      setSuccess(`Marca actualizada con éxito.`);
      setEditingBrand(null);
      loadData();
    } catch (err) {
      setError(err.message || "No se pudo actualizar la marca.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteBrand = (b) => {
    setConfirmConfig({
      isOpen: true,
      title: "Eliminar Marca",
      message: `¿Estás seguro de que deseas eliminar la marca "${b.nombre}"? Esto afectará a los vehículos asociados.`,
      confirmColor: "#e11d48",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteBrand(b.id);
          setSuccess(`Marca "${b.nombre}" eliminada.`);
          loadData();
        } catch (err) {
          setError(err.message || "No se pudo eliminar la marca.");
        } finally {
          setSaving(false);
        }
      }
    });
  };

  // ── ACCIONES: TIPOS (ADMIN ONLY) ────────────────────────────────
  const handleCreateTypeSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await createVehicleType({ nombre: creatingType.nombre });
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
      await updateVehicleType(editingType.id, { nombre: editingType.nombre });
      setSuccess(`Tipo de vehículo actualizado con éxito.`);
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
      message: `¿Estás seguro de que deseas eliminar el tipo de vehículo "${t.nombre}"? Esto afectará a los vehículos asociados.`,
      confirmColor: "#e11d48",
      onConfirm: async () => {
        try {
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
          setSaving(true);
          await deleteVehicleType(t.id);
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
    return <Loader label="Cargando información..." />;
  }

  // Filtrado de vehículos en frontend
  const filteredVehicles = vehicles.filter((v) => {
    if (filterType === "MY" && v.propietario_usuario_id !== user?.id) {
      return false;
    }
    const query = vehiclesSearchQuery.toLowerCase();
    const plate = v.placa?.toLowerCase() || "";
    const brand = v.marca?.nombre?.toLowerCase() || "";
    const ownerName = v.propietario ? `${v.propietario.nombre} ${v.propietario.apellido_paterno}`.toLowerCase() : "";
    return plate.includes(query) || brand.includes(query) || ownerName.includes(query);
  });

  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentVehicles = filteredVehicles.slice(indexOfFirstItem, indexOfLastItem);

  return (
    <section className="page-stack">
      {/* Cabecera Principal */}
      <div className="hero card">
        <p className="eyebrow">Gestión</p>
        <h2>Control de Vehículos y Catálogos</h2>
        <p className="muted-text">
          Registra vehículos autorizados y gestiona las marcas y categorías oficiales del campus.
        </p>
      </div>

      {/* Selector de pestañas para administradores */}
      {isAdmin && (
        <div style={{ display: "flex", gap: "1rem", borderBottom: "2px solid rgba(21, 62, 117, 0.1)", paddingBottom: "0.5rem", marginBottom: "1.5rem" }}>
          <button
            type="button"
            onClick={() => { setActiveTab("vehicles"); setError(""); setSuccess(""); }}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === "vehicles" ? "3px solid var(--color-primary)" : "none",
              color: activeTab === "vehicles" ? "var(--color-primary)" : "#666",
              padding: "0.5rem 1rem",
              fontWeight: "bold",
              cursor: "pointer"
            }}
          >
            Vehículos
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab("brands"); setError(""); setSuccess(""); }}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === "brands" ? "3px solid var(--color-primary)" : "none",
              color: activeTab === "brands" ? "var(--color-primary)" : "#666",
              padding: "0.5rem 1rem",
              fontWeight: "bold",
              cursor: "pointer"
            }}
          >
            Gestionar Marcas
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
            Gestionar Tipos de Vehículo
          </button>
        </div>
      )}

      {success && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}><p style={{ color: "green", fontWeight: "bold", background: "#e6ffe6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid green", margin: 0 }}>{success}</p></div>}
      {error && <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}><p className="error-text" style={{ background: "#ffe6e6", padding: "0.5rem 1rem", borderRadius: "8px", border: "1px solid red", display: "inline-block", margin: 0 }}>{error}</p></div>}

      {/* ── CONTENIDO DE LA PESTAÑA: VEHÍCULOS ────────────────────────── */}
      {activeTab === "vehicles" && (
        <>
          <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
            <div>
              <p className="eyebrow">Vehículos</p>
              <h3>{isStaff ? "Todos los vehículos del sistema" : "Vehículos registrados bajo mi cuenta"}</h3>
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="button" onClick={handleOpenCreateVehicle} style={{ padding: "0.6rem 1.2rem" }}>
                Registrar Vehículo
              </button>
            </div>
          </div>

          <SearchBar
            searchQuery={vehiclesSearchQuery}
            setSearchQuery={(val) => { setVehiclesSearchQuery(val); setCurrentPage(1); }}
            placeholder="Buscar vehículos por placa, marca o propietario..."
            onRefresh={loadData}
            isRefreshing={loading}
            refreshTitle="Refrescar"
          />

          {!filteredVehicles.length && (
            <div className="card">
              <p className="muted-text text-center">No se encontraron vehículos registrados bajo esta selección.</p>
            </div>
          )}

          {filteredVehicles.length > 0 && (
            <div className="card" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
                    <th style={{ padding: "1rem" }}>Foto</th>
                    <th style={{ padding: "1rem" }}>Placa</th>
                    <th style={{ padding: "1rem" }}>Marca</th>
                    <th style={{ padding: "1rem" }}>Color</th>
                    <th style={{ padding: "1rem" }}>Propietario</th>
                    <th style={{ padding: "1rem", textAlign: "right" }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {currentVehicles.map((v) => (
                    <tr key={v.id} style={{ borderBottom: "1px solid rgba(21, 62, 117, 0.05)" }}>
                      <td style={{ padding: "1rem" }}>
                        {v.foto_id && vehiclePhotoUrls[v.foto_id] ? (
                          <img
                            src={vehiclePhotoUrls[v.foto_id]}
                            alt={`Foto del vehículo ${v.placa}`}
                            style={{ width: "84px", height: "84px", objectFit: "cover", borderRadius: "10px", border: "1px solid rgba(21, 62, 117, 0.15)", cursor: "pointer" }}
                            onClick={() => setZoomedImage(vehiclePhotoUrls[v.foto_id])}
                            title="Ver foto en tamaño completo"
                          />
                        ) : (
                          <span className="muted-text">Sin foto</span>
                        )}
                      </td>
                      <td style={{ padding: "1rem" }}>
                        <span 
                          style={{ 
                            fontFamily: "monospace", 
                            fontSize: "1rem", 
                            fontWeight: "bold", 
                            background: "#e6f2ff", 
                            color: "#153e75", 
                            padding: "0.25rem 0.5rem", 
                            borderRadius: "4px" 
                          }}
                        >
                          {v.placa}
                        </span>
                      </td>
                      <td style={{ padding: "1rem", fontWeight: "bold" }}>
                        {v.marca?.nombre || "N/A"}
                      </td>
                      <td style={{ padding: "1rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <div
                            style={{
                              width: "16px",
                              height: "16px",
                              borderRadius: "50%",
                              backgroundColor: getColorHex(v.color),
                              border: "1px solid rgba(0,0,0,0.15)",
                              flexShrink: 0
                            }}
                          />
                          <span>{v.color}</span>
                        </div>
                      </td>
                      <td style={{ padding: "1rem" }}>
                        {v.propietario ? `${v.propietario.nombre} ${v.propietario.apellido_paterno}` : "N/A"}
                      </td>
                      <td style={{ padding: "1rem", textAlign: "right", display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          onClick={() => handleOpenEditVehicle(v)}
                          title="Editar vehículo"
                          style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-primary)", color: "white", border: "none", cursor: "pointer" }}
                        >
                          <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>edit</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleOpenVehicleDetails(v)}
                          title="Ver detalles"
                          style={{ width: "34px", height: "34px", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", background: "#0f766e", color: "white", border: "none", cursor: "pointer" }}
                        >
                          <span className="material-symbols-rounded" style={{ fontSize: "18px" }}>visibility</span>
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleDeleteVehicle(v)}
                          title="Eliminar vehículo"
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

          {filteredVehicles.length > 0 && (
            <Pagination
              currentPage={currentPage}
              totalItems={filteredVehicles.length}
              itemsPerPage={itemsPerPage}
              onPageChange={setCurrentPage}
            />
          )}
        </>
      )}

      {/* ── CONTENIDO DE LA PESTAÑA: MARCAS ─────────────────────────── */}
      {activeTab === "brands" && isAdmin && (
        <>
          <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
            <div>
              <p className="eyebrow">Catálogos</p>
              <h3>Marcas de Vehículos</h3>
            </div>
            <button type="button" onClick={() => setCreatingBrand({ nombre: "" })} style={{ padding: "0.6rem 1.2rem" }}>
              Agregar Nueva Marca
            </button>
          </div>

          {!brands.length && (
            <div className="card">
              <p className="muted-text text-center">No hay marcas registradas en el sistema.</p>
            </div>
          )}

          {brands.length > 0 && (
            <div className="card" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
                    <th style={{ padding: "1rem" }}>Nombre de la Marca</th>
                    <th style={{ padding: "1rem" }}>ID</th>
                    <th style={{ padding: "1rem", textAlign: "right" }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {brands.map((b) => (
                    <tr key={b.id} style={{ borderBottom: "1px solid rgba(21, 62, 117, 0.05)" }}>
                      <td style={{ padding: "1rem", fontWeight: "bold" }}>
                        {b.nombre}
                      </td>
                      <td style={{ padding: "1rem", fontFamily: "monospace", fontSize: "0.85rem", color: "#666" }}>
                        {b.id}
                      </td>
                      <td style={{ padding: "1rem", textAlign: "right", display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          onClick={() => setEditingBrand({ id: b.id, nombre: b.nombre })}
                          style={{ fontSize: "0.75rem", padding: "0.4rem 0.8rem", background: "var(--color-primary)" }}
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleDeleteBrand(b)}
                          style={{ fontSize: "0.75rem", padding: "0.4rem 0.8rem" }}
                        >
                          Eliminar
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

      {/* ── CONTENIDO DE LA PESTAÑA: TIPOS ──────────────────────────── */}
      {activeTab === "types" && isAdmin && (
        <>
          <div className="section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "1rem" }}>
            <div>
              <p className="eyebrow">Catálogos</p>
              <h3>Tipos de Vehículos</h3>
            </div>
            <button type="button" onClick={() => setCreatingType({ nombre: "" })} style={{ padding: "0.6rem 1.2rem" }}>
              Agregar Nuevo Tipo
            </button>
          </div>

          {!types.length && (
            <div className="card">
              <p className="muted-text text-center">No hay tipos de vehículos registrados en el sistema.</p>
            </div>
          )}

          {types.length > 0 && (
            <div className="card" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
                    <th style={{ padding: "1rem" }}>Categoría / Tipo</th>
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
                      <td style={{ padding: "1rem", textAlign: "right", display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          onClick={() => setEditingType({ id: t.id, nombre: t.nombre })}
                          style={{ fontSize: "0.75rem", padding: "0.4rem 0.8rem", background: "var(--color-primary)" }}
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleDeleteType(t)}
                          style={{ fontSize: "0.75rem", padding: "0.4rem 0.8rem" }}
                        >
                          Eliminar
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

      {/* ── MODALES: VEHÍCULOS ──────────────────────────────────────── */}
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
                    placeholder="1234ABC"
                    className={validatePlateForm(creatingVehicle.placa).className}
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
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input
                      type="text"
                      placeholder="Ej. Rojo"
                      value={creatingVehicle.color}
                      onChange={(event) =>
                        setCreatingVehicle((current) => ({
                          ...current,
                          color: event.target.value.toUpperCase()
                        }))
                      }
                      required
                      style={{ flex: 1 }}
                    />
                    <input
                      type="color"
                      value={getColorHex(creatingVehicle.color)}
                      onChange={(event) => {
                        const hex = event.target.value;
                        const closest = getClosestColorName(hex);
                        setCreatingVehicle((current) => ({
                          ...current,
                          color: closest
                        }));
                      }}
                      style={{
                        width: "100px",
                        height: "42px",
                        padding: "2px",
                        border: "1px solid #cbd5e1",
                        borderRadius: "8px",
                        cursor: "pointer",
                        flexShrink: 0
                      }}
                    />
                  </div>
                </label>

                <label className="field-group">
                  <span>Marca</span>
                  {brands.length > 0 ? (
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
                  ) : (
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", color: "#e11d48", background: "#fef2f2", border: "1px solid #fee2e2", padding: "0.5rem 0.8rem", borderRadius: "6px", fontSize: "0.85rem", marginTop: "5px" }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: "2px" }}><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      <span>No hay marcas registradas. Agrégalas en la pestaña "Gestionar Marcas" primero.</span>
                    </div>
                  )}
                </label>

                <label className="field-group">
                  <span>Tipo de Vehículo</span>
                  {types.length > 0 ? (
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
                  ) : (
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", color: "#e11d48", background: "#fef2f2", border: "1px solid #fee2e2", padding: "0.5rem 0.8rem", borderRadius: "6px", fontSize: "0.85rem", marginTop: "5px" }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: "2px" }}><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                      <span>No hay tipos de vehículos registrados. Agrégalas en la pestaña "Gestionar Tipos" primero.</span>
                    </div>
                  )}
                </label>
                {isStaff ? (
                  <label className="field-group">
                    <span>Propietario Asociado</span>
                    {users.length > 0 ? (
                       <select
                        value={creatingVehicle.propietario_usuario_id}
                        onChange={(event) =>
                          setCreatingVehicle((current) => ({
                            ...current,
                            propietario_usuario_id: event.target.value
                          }))
                        }
                        required
                      >
                        {users.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.nombre} {u.apellido_paterno} ({u.carnet})
                          </option>
                        ))}
                      </select>
                    ) : (
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", color: "#e11d48", background: "#fef2f2", border: "1px solid #fee2e2", padding: "0.5rem 0.8rem", borderRadius: "6px", fontSize: "0.85rem", marginTop: "5px" }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: "2px" }}><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                        <span>No hay usuarios registrados en el sistema.</span>
                      </div>
                    )}
                  </label>
                ) : (
                  <div style={{ gridColumn: "1 / -1", display: "flex", gap: "0.5rem", alignItems: "center", background: "#f0f9ff", border: "1px solid #e0f2fe", padding: "0.6rem 1rem", borderRadius: "8px", fontSize: "0.85rem", color: "#0369a1" }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                    <span>El vehículo se registrará bajo tu propio nombre: <strong>{user?.nombre} {user?.apellido_paterno}</strong>.</span>
                  </div>
                )}
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
                  <small className="muted-text">Opcional. Se guarda de forma privada junto al registro.</small>
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

      {/* Modal de Detalles de Vehículo */}
      {viewingVehicle && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large" style={{ maxWidth: "720px" }}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Detalle</p>
                <h2>Información del vehículo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setViewingVehicle(null)}>
                Cerrar
              </button>
            </div>

            <div className="form-block">
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "center" }}>
                  <div style={{ width: "min(260px, 100%)", aspectRatio: "1 / 1", background: "#f8fafc", borderRadius: "16px", border: "1px solid rgba(21, 62, 117, 0.12)", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {viewingVehicle.foto_id && vehiclePhotoUrls[viewingVehicle.foto_id] ? (
                      <img
                        src={vehiclePhotoUrls[viewingVehicle.foto_id]}
                        alt={`Foto del vehículo ${viewingVehicle.placa}`}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />
                    ) : (
                      <span className="muted-text">Sin foto registrada</span>
                    )}
                  </div>
                </div>

                <div className="details-grid" style={{ display: "grid", gap: "0.8rem" }}>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.9rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Placa</p>
                    <p style={{ margin: 0, fontSize: "1.1rem", fontWeight: "700", fontFamily: "monospace" }}>{viewingVehicle.placa}</p>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.8rem" }}>
                    <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                      <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Marca</p>
                      <p style={{ margin: 0, fontWeight: "600" }}>{viewingVehicle.marca?.nombre || "N/A"}</p>
                    </div>
                    <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                      <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Tipo</p>
                      <p style={{ margin: 0, fontWeight: "600" }}>{viewingVehicle.tipo?.nombre || "N/A"}</p>
                    </div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.8rem" }}>
                    <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                      <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Color</p>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.25rem" }}>
                        <div
                          style={{
                            width: "20px",
                            height: "20px",
                            borderRadius: "50%",
                            backgroundColor: getColorHex(viewingVehicle.color),
                            border: "1px solid rgba(0,0,0,0.15)",
                            flexShrink: 0
                          }}
                        />
                        <p style={{ margin: 0, fontWeight: "600" }}>{viewingVehicle.color || "N/A"}</p>
                      </div>
                    </div>
                    <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.8rem 1rem" }}>
                      <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Carnet / Registro</p>
                      <p style={{ margin: 0, fontWeight: "600" }}>{viewingVehicle.propietario?.carnet || "N/A"}</p>
                    </div>
                  </div>
                  <div style={{ background: "#f8fafc", border: "1px solid rgba(21, 62, 117, 0.12)", borderRadius: "10px", padding: "0.9rem 1rem" }}>
                    <p className="eyebrow" style={{ marginBottom: "0.25rem" }}>Propietario</p>
                    <p style={{ margin: 0, fontWeight: "600" }}>
                      {viewingVehicle.propietario ? `${viewingVehicle.propietario.nombre} ${viewingVehicle.propietario.apellido_paterno}` : "N/A"}
                    </p>
                  </div>
                </div>
              </div>
            </div>

          </div>
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
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                <div style={{ width: "min(220px, 100%)", aspectRatio: "1 / 1", background: "#f8fafc", borderRadius: "16px", border: "1px solid rgba(21, 62, 117, 0.12)", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {editingVehicle.foto_id && vehiclePhotoUrls[editingVehicle.foto_id] ? (
                    <img
                      src={vehiclePhotoUrls[editingVehicle.foto_id]}
                      alt={`Foto actual del vehículo ${editingVehicle.placa}`}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  ) : (
                    <span className="muted-text">Sin foto guardada</span>
                  )}
                </div>
                <div style={{ width: "100%", maxWidth: "320px" }}>
                  <label className="field-group" style={{ marginBottom: 0 }}>
                    <span>Foto privada del vehículo</span>
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
                    <small className="muted-text">Puedes subir una nueva foto para reemplazar la actual.</small>
                  </label>
                </div>
              </div>
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
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input
                      type="text"
                      value={editingVehicle.color}
                      onChange={(event) =>
                        setEditingVehicle((current) => ({
                          ...current,
                          color: event.target.value.toUpperCase()
                        }))
                      }
                      required
                      style={{ flex: 1 }}
                    />
                    <input
                      type="color"
                      value={getColorHex(editingVehicle.color)}
                      onChange={(event) => {
                        const hex = event.target.value;
                        const closest = getClosestColorName(hex);
                        setEditingVehicle((current) => ({
                          ...current,
                          color: closest
                        }));
                      }}
                      style={{
                        width: "100px",
                        height: "42px",
                        padding: "2px",
                        border: "1px solid #cbd5e1",
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

                {isStaff && (
                  <label className="field-group">
                    <span>Propietario Asociado</span>
                    <select
                      value={editingVehicle.propietario_usuario_id}
                      onChange={(event) =>
                        setEditingVehicle((current) => ({
                          ...current,
                          propietario_usuario_id: event.target.value
                        }))
                      }
                      required
                    >
                      {users.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.nombre} {u.apellido_paterno} ({u.carnet})
                        </option>
                      ))}
                    </select>
                  </label>
                )}

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

      {/* ── MODALES: MARCAS (ADMIN ONLY) ────────────────────────────── */}
      {creatingBrand && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleCreateBrandSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Catálogos</p>
                <h2>Agregar Nueva Marca</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setCreatingBrand(null)}>Cerrar</button>
            </div>
            <div className="form-block">
              <label className="field-group">
                <span>Nombre de la Marca</span>
                <input
                  type="text"
                  placeholder="Ej. Toyota, Suzuki"
                  value={creatingBrand.nombre}
                  onChange={(e) => setCreatingBrand({ nombre: e.target.value })}
                  required
                />
              </label>
            </div>
            <div className="modal-actions" style={{ marginTop: "1rem" }}>
              <button type="submit" disabled={saving}>
                {saving ? "Registrando..." : "Registrar Marca"}
              </button>
            </div>
          </form>
        </div>
      )}

      {editingBrand && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleEditBrandSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Catálogos</p>
                <h2>Editar Marca</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setEditingBrand(null)}>Cerrar</button>
            </div>
            <div className="form-block">
              <label className="field-group">
                <span>Nombre de la Marca</span>
                <input
                  type="text"
                  value={editingBrand.nombre}
                  onChange={(e) => setEditingBrand(prev => ({ ...prev, nombre: e.target.value }))}
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

      {/* ── MODALES: TIPOS (ADMIN ONLY) ─────────────────────────────── */}
      {creatingType && (
        <div className="modal-backdrop">
          <form className="modal-card modal-large registration-form" onSubmit={handleCreateTypeSubmit}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Catálogos</p>
                <h2>Agregar Nuevo Tipo de Vehículo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setCreatingType(null)}>Cerrar</button>
            </div>
            <div className="form-block">
              <label className="field-group">
                <span>Nombre del Tipo / Categoría</span>
                <input
                  type="text"
                  placeholder="Ej. Vagoneta, Motocicleta, Camión"
                  value={creatingType.nombre}
                  onChange={(e) => setCreatingType({ nombre: e.target.value })}
                  required
                />
              </label>
            </div>
            <div className="modal-actions" style={{ marginTop: "1rem" }}>
              <button type="submit" disabled={saving}>
                {saving ? "Registrando..." : "Registrar Tipo"}
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
                <h2>Editar Tipo de Vehículo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => setEditingType(null)}>Cerrar</button>
            </div>
            <div className="form-block">
              <label className="field-group">
                <span>Nombre del Tipo</span>
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

      {/* Modal de Confirmación General */}
      <ConfirmModal
        isOpen={confirmConfig.isOpen}
        title={confirmConfig.title}
        message={confirmConfig.message}
        confirmColor={confirmConfig.confirmColor}
        onConfirm={confirmConfig.onConfirm}
        onCancel={() => setConfirmConfig({ ...confirmConfig, isOpen: false })}
      />

      {/* Modal de Zoom de Imagen */}
      {zoomedImage && (
        <div 
          className="modal-backdrop" 
          onClick={() => setZoomedImage(null)} 
          style={{ cursor: "zoom-out", zIndex: 1000 }}
          title="Hacer clic para cerrar"
        >
          <div 
            style={{ 
              position: "relative",
              maxWidth: "90%",
              maxHeight: "90%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <img 
              src={zoomedImage} 
              alt="Foto ampliada" 
              style={{ 
                maxWidth: "100%", 
                maxHeight: "80vh", 
                borderRadius: "12px", 
                boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
                border: "4px solid white",
                objectFit: "contain",
                display: "block"
              }} 
            />
            <button
              type="button"
              onClick={() => setZoomedImage(null)}
              style={{
                position: "absolute",
                top: "-15px",
                right: "-15px",
                width: "36px",
                height: "36px",
                borderRadius: "50%",
                background: "#ffffff",
                color: "#1e293b",
                border: "none",
                boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                fontSize: "18px",
                fontWeight: "bold",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}
              title="Cerrar"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export default Vehicles;
