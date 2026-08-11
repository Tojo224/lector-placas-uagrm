import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import ConfirmModal from "../ConfirmModal";

function Sidebar({ isOpen, onClose }) {
  const { user, signOut } = useAuth();
  const [isLogoutConfirmOpen, setIsLogoutConfirmOpen] = useState(false);

  const links = [];

  if (user?.rol === "ADMINISTRADOR") {
    links.push(
      { to: "/dashboard", label: "Dashboard" },
      { to: "/subir-placa", label: "Escanear Placas" },
      { to: "/vehiculos", label: "Gestionar Vehículos" },
      { to: "/usuarios", label: "Gestionar Usuarios" },
      { to: "/dispositivos", label: "Gestionar Dispositivos" },
      { to: "/accesos", label: "Control de Accesos" },
      { to: "/solicitudes-vehiculos", label: "Solicitudes de Vehículos" }
    );
  } else if (user?.rol === "OPERADOR") {
    links.push(
      { to: "/subir-placa", label: "Escanear Placas" },
      { to: "/vehiculos", label: "Gestionar Vehículos" },
      { to: "/accesos", label: "Control de Accesos" },
      { to: "/solicitudes-vehiculos", label: "Solicitudes de Vehículos" }
    );
  } else if (user?.rol === "DISPOSITIVO") {
    links.push(
      { to: "/subir-placa", label: "Escanear Placas" }
    );
  } else {
    links.push(
      { to: "/", label: "Inicio" },
      { to: "/vehiculos", label: "Mis Vehículos" },
      { to: "/accesos", label: "Control de Accesos" }
    );
  }

  if (user?.rol !== "DISPOSITIVO") {
    links.push({ to: "/perfil", label: "Perfil" });
  }

  return (
    <>
      <aside className={isOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand">Placas App</div>
        <nav className="sidebar-nav">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              title={link.label}
              onClick={onClose}
              className={({ isActive }) =>
                isActive ? "nav-link nav-link-icon active" : "nav-link nav-link-icon"
              }
            >
              <span className="nav-text">{link.label}</span>
            </NavLink>
          ))}
          {user?.rol !== "DISPOSITIVO" && (
            <button
              type="button"
              onClick={() => setIsLogoutConfirmOpen(true)}
              className="nav-link nav-link-icon"
              style={{
                background: "rgba(220, 38, 38, 0.15)",
                border: "1px solid rgba(220, 38, 38, 0.3)",
                borderRadius: "8px",
                textAlign: "left",
                width: "calc(100% - 1.5rem)",
                cursor: "pointer",
                color: "#f87171",
                padding: "0.75rem 1rem",
                margin: "auto 0.75rem 0.75rem 0.75rem",
                marginTop: "auto"
              }}
            >
              <span className="nav-text" style={{ fontWeight: "700" }}>Cerrar Sesión</span>
            </button>
          )}
        </nav>
      </aside>
      {isOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          onClick={onClose}
          aria-label="Cerrar menu"
        />
      )}
      <ConfirmModal
        isOpen={isLogoutConfirmOpen}
        title="Cerrar Sesión"
        message="¿Estás seguro de que deseas cerrar tu sesión en el sistema?"
        confirmColor="var(--color-danger, #ef4444)"
        onConfirm={() => {
          setIsLogoutConfirmOpen(false);
          signOut();
          onClose();
        }}
        onCancel={() => setIsLogoutConfirmOpen(false)}
      />
    </>
  );
}

export default Sidebar;
