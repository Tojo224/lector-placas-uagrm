import { Navigate, Route, Routes } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import Dashboard from "../pages/admin/Dashboard";
import Login from "../pages/auth/Login";
import Profile from "../pages/Profile";
import UploadPlate from "../pages/device/UploadPlate";
import Users from "../pages/admin/Users";
import Vehicles from "../pages/operator/Vehicles";
import UserVehicles from "../pages/user/UserVehicles";
import UserDashboard from "../pages/user/UserDashboard";
import UserAccessLogs from "../pages/user/UserAccessLogs";
import Devices from "../pages/admin/Devices";
import AccessLogs from "../pages/operator/AccessLogs";
import VehicleRegistrationRequests from "../pages/VehicleRegistrationRequests";
import Loader from "../components/Loader";
import { useAuth } from "../hooks/useAuth";
import { isEdgeHosted } from "../api/edge";
import EdgeProvisioning from "../pages/device/EdgeProvisioning";

function VehiclesRoute() {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return <Loader label="Cargando ruta..." />;
  }

  if (user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR") {
    return <Vehicles />;
  }

  return <UserVehicles />;
}

function AccessLogsRoute() {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return <Loader label="Cargando ruta..." />;
  }

  if (user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR") {
    return <AccessLogs />;
  }

  return <UserAccessLogs />;
}


function ProtectedLayout() {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return <Loader label="Validando acceso..." />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <DashboardLayout />;
}

function AdminRoute({ children }) {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return <Loader label="Validando rol..." />;
  }

  if (user?.rol !== "ADMINISTRADOR") {
    return <Navigate to="/" replace />;
  }

  return children;
}

function PlateScannerRoute({ children }) {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return <Loader label="Validando rol..." />;
  }

  if (!["ADMINISTRADOR", "OPERADOR", "DISPOSITIVO"].includes(user?.rol)) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function EdgeScannerRoute({ children }) {
  const { user, authLoading } = useAuth();
  if (authLoading) return <Loader label="Validando acceso local..." />;
  if (!user || !["ADMINISTRADOR", "OPERADOR"].includes(user.rol)) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function HomeRoute() {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return <Loader label="Cargando..." />;
  }

  if (user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR") {
    return <Dashboard />;
  }

  if (user?.rol === "DISPOSITIVO") {
    return <Navigate to="/subir-placa" replace />;
  }

  return <UserDashboard />;
}

function AppRoutes() {
  if (isEdgeHosted) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<EdgeScannerRoute><UploadPlate /></EdgeScannerRoute>} />
        <Route path="/subir-placa" element={<EdgeScannerRoute><UploadPlate /></EdgeScannerRoute>} />
        <Route path="/configuracion" element={<EdgeProvisioning />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/registro" element={<Navigate to="/login" replace />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/dashboard" element={<HomeRoute />} />
        <Route path="/subir-placa" element={<PlateScannerRoute><UploadPlate /></PlateScannerRoute>} />
        <Route path="/perfil" element={<Profile />} />
        <Route path="/usuarios" element={<AdminRoute><Users /></AdminRoute>} />
        <Route path="/dispositivos" element={<AdminRoute><Devices /></AdminRoute>} />
        <Route path="/vehiculos" element={<VehiclesRoute />} />
        <Route path="/accesos" element={<AccessLogsRoute />} />
        <Route path="/solicitudes-vehiculos" element={<VehicleRegistrationRequests />} />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
