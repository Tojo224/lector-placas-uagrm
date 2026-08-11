import { useEffect, useState, useCallback } from "react";
import Loader from "../../components/Loader";
import { getDashboardSummary, getPlateScans, getAccessLogs, getMediaUrl } from "../../api/plates";
import { useAuth } from "../../hooks/useAuth";
import parseApiError from "../../utils/errors";

// ── Iconos SVG Profesionales ──────────────────────────────────────────────────
const Icons = {
  Car: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2" />
      <circle cx="7" cy="17" r="2" />
      <path d="M9 17h6" />
      <circle cx="17" cy="17" r="2" />
    </svg>
  ),
  ShieldCheck: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 11 2 2 4-4" />
    </svg>
  ),
  Camera: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
      <circle cx="12" cy="13" r="3" />
    </svg>
  ),
  Database: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
    </svg>
  ),
  Award: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="7" />
      <path d="M8.21 13.89 7 23l5-3 5 3-1.21-9.12" />
    </svg>
  ),
  Users: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  ArrowUpDown: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21 16-4 4-4-4M17 20V4M3 8l4-4 4 4M7 4v16" />
    </svg>
  ),
  GraduationCap: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
      <path d="M6 12v5c0 2 2 3 6 3s6-1 6-3v-5" />
    </svg>
  ),
  Calendar: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
      <line x1="16" x2="16" y1="2" y2="6"/>
      <line x1="8" x2="8" y1="2" y2="6"/>
      <line x1="3" x2="21" y1="10" y2="10"/>
    </svg>
  ),
  Activity: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  Search: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/>
      <path d="m21 21-4.3-4.3"/>
    </svg>
  )
};

const kpiCardBase = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  gap: "0.5rem",
  borderRadius: "12px",
  padding: "0.85rem 1rem",
  background: "#ffffff",
  boxShadow: "0 6px 20px rgba(15, 23, 42, 0.04)",
  border: "1px solid rgba(15, 23, 42, 0.06)",
};

const kpiLabelStyle = {
  margin: 0,
  fontSize: "0.72rem",
  color: "#64748b",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
};

const kpiValueStyle = {
  fontSize: "1.75rem",
  fontWeight: "800",
  lineHeight: 1.1,
};

function BarChart({ data, labelKey, valueKey, title, icon, color = "#153e75" }) {
  const max = Math.max(...data.map(d => d[valueKey]), 1);
  return (
    <div style={{ background: "white", borderRadius: "12px", padding: "1rem", boxShadow: "0 2px 10px rgba(21,62,117,0.06)", border: "1px solid rgba(21,62,117,0.06)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1.2rem" }}>
        <span style={{ color, display: "flex", alignItems: "center" }}>{icon}</span>
        <h4 style={{ margin: 0, color: "#153e75", fontSize: "0.95rem", fontWeight: 700 }}>{title}</h4>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {data.map((d, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span style={{ width: "90px", fontSize: "0.78rem", color: "#64748b", textAlign: "right", flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {d[labelKey]}
            </span>
            <div style={{ flex: 1, background: "rgba(21,62,117,0.07)", borderRadius: "8px", height: "22px", overflow: "hidden" }}>
              <div style={{
                width: `${(d[valueKey] / max) * 100}%`,
                minWidth: d[valueKey] > 0 ? "6px" : 0,
                height: "100%",
                background: `linear-gradient(90deg, ${color}, ${color}bb)`,
                borderRadius: "8px",
                transition: "width 0.6s cubic-bezier(.22,.68,0,1.2)",
              }} />
            </div>
            <span style={{ fontSize: "0.82rem", fontWeight: 700, color, width: "28px", textAlign: "right", flexShrink: 0 }}>{d[valueKey]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DonutChart({ segments, title, icon }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  let cumulative = 0;
  const r = 60;
  const cx = 75, cy = 75;

  const paths = segments.map((seg) => {
    const startAngle = (cumulative / total) * 2 * Math.PI - Math.PI / 2;
    cumulative += seg.value;
    const endAngle = (cumulative / total) * 2 * Math.PI - Math.PI / 2;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const largeArc = seg.value / total > 0.5 ? 1 : 0;
    const ri = 35;
    const xi1 = cx + ri * Math.cos(startAngle);
    const yi1 = cy + ri * Math.sin(startAngle);
    const xi2 = cx + ri * Math.cos(endAngle);
    const yi2 = cy + ri * Math.sin(endAngle);
    const d = `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} L ${xi2} ${yi2} A ${ri} ${ri} 0 ${largeArc} 0 ${xi1} ${yi1} Z`;
    return { ...seg, d };
  });

  return (
    <div style={{ background: "white", borderRadius: "12px", padding: "1rem", boxShadow: "0 2px 10px rgba(21,62,117,0.06)", border: "1px solid rgba(21,62,117,0.06)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
        <span style={{ color: "#153e75", display: "flex", alignItems: "center" }}>{icon}</span>
        <h4 style={{ margin: 0, color: "#153e75", fontSize: "0.95rem", fontWeight: 700 }}>{title}</h4>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", flexWrap: "wrap" }}>
        <svg width="150" height="150" viewBox="0 0 150 150">
          {paths.map((p, i) => (
            <path key={i} d={p.d} fill={p.color} opacity="0.9" />
          ))}
          <text x={cx} y={cy + 6} textAnchor="middle" fontSize="16" fontWeight="800" fill="#153e75">{total}</text>
        </svg>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {segments.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <div style={{ width: "12px", height: "12px", borderRadius: "3px", background: s.color, flexShrink: 0 }} />
              <span style={{ fontSize: "0.82rem", color: "#475569" }}>
                {s.label} <strong style={{ color: "#153e75" }}>{s.value}</strong>
                <span style={{ color: "#94a3b8" }}> ({total > 0 ? Math.round((s.value / total) * 100) : 0}%)</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Dashboard() {
  const { user } = useAuth();
  const [dashboardData, setDashboardData] = useState(null);
  const [scans, setScans] = useState([]);
  const [accesses, setAccesses] = useState([]);
  const [vehiclePhotoUrls, setVehiclePhotoUrls] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadDashboard = useCallback(async (showSpinner = true) => {
    try {
      if (showSpinner) setLoading(true);
      else setIsRefreshing(true);
      
      const filterId = user?.rol === "ADMINISTRADOR" ? undefined : user?.id;
      const [data, sc, ac] = await Promise.all([
        getDashboardSummary(filterId),
        getPlateScans(),
        getAccessLogs()
      ]);
      
      setDashboardData(data);
      setScans(sc || []);
      setAccesses(ac || []);
    } catch (loadError) {
      setError(parseApiError(loadError, "No se pudo cargar el resumen del dashboard."));
      console.error(loadError);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [user?.id, user?.role]);

  useEffect(() => {
    if (user?.id) {
      loadDashboard(true);
    }
  }, [user?.id, loadDashboard]);

  const recentScans = dashboardData?.recent_scans || [];

  useEffect(() => {
    let cancelled = false;
    const photoIds = [...new Set(recentScans.map((scan) => scan.vehicle_photo_id).filter(Boolean))];

    if (!photoIds.length) {
      setVehiclePhotoUrls({});
      return () => { cancelled = true; };
    }

    Promise.all(
      photoIds.map(async (id) => {
        try {
          const { url } = await getMediaUrl(id);
          return [id, url];
        } catch {
          return [id, ""];
        }
      })
    ).then((entries) => {
      if (!cancelled) {
        setVehiclePhotoUrls(Object.fromEntries(entries));
      }
    });

    return () => { cancelled = true; };
  }, [dashboardData]);

  if (loading) {
    return <Loader label="Cargando resumen de telemetría..." />;
  }

  // ── Derivar datos para gráficas ──────────────────────────────────────────
  const scansByStatus = [
    { label: "Detectado",       value: scans.filter(s => s.estado === "DETECTADO").length,       color: "#10b981" },
    { label: "Baja confianza",  value: scans.filter(s => s.estado === "BAJA_CONFIANZA").length,  color: "#f59e0b" },
    { label: "Manual",          value: scans.filter(s => s.estado === "MANUAL").length,          color: "#3b82f6" },
    { label: "Error",           value: scans.filter(s => s.estado === "ERROR").length,           color: "#ef4444" },
  ].filter(s => s.value > 0);

  const accessesByDir = [
    { label: "Entradas", value: accesses.filter(a => a.tipo_acceso === "ENTRADA").length, color: "#10b981" },
    { label: "Salidas",  value: accesses.filter(a => a.tipo_acceso === "SALIDA").length,  color: "#153e75" },
  ];

  // Escaneos por día (últimos 7 días)
  const last7 = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    const key = d.toISOString().slice(0, 10);
    return {
      label: d.toLocaleDateString("es-BO", { timeZone: "America/La_Paz", weekday: "short", day: "numeric" }),
      value: scans.filter(s => s.creado_el?.slice(0, 10) === key).length,
    };
  });

  return (
    <section className="page-stack">
      <div className="hero card" style={{ position: "relative" }}>
        <p className="eyebrow">Resumen de Telemetría</p>
        <h2>Panel de Control ({user?.rol === "ADMINISTRADOR" ? "Administrador" : "Operador"})</h2>
        <p className="muted-text">
          Estadísticas y bitácora en tiempo real de los accesos vehiculares controlados por Inteligencia Artificial local.
        </p>
        
        <button
          type="button"
          className="ghost-button"
          onClick={() => loadDashboard(false)}
          disabled={isRefreshing}
          style={{
            position: "absolute",
            top: "1.5rem",
            right: "1.5rem",
            padding: "0.6rem",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            background: "rgba(21, 62, 117, 0.05)",
            border: "1px solid rgba(21, 62, 117, 0.1)",
            borderRadius: "8px",
            cursor: "pointer"
          }}
          title="Refrescar datos"
        >
          <svg
            width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            style={{ animation: isRefreshing ? "spin 1s linear infinite" : "none" }}
          >
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.59-9.21l5.67-5.67"/>
          </svg>
          {isRefreshing ? "Actualizando…" : "Refrescar"}
        </button>
      </div>

      {error && <p className="error-text" style={{ background: "#ffe6e6", padding: "0.8rem", borderRadius: "8px", border: "1px solid red" }}>{error}</p>}

      {/* Grid de KPIs Premium con Iconos Profesionales */}
      <div className="details-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.5rem" }}>
        
        {/* KPI 1: Vehículos Registrados */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid var(--color-primary)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Vehículos Registrados</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "var(--color-primary)" }}>
              {dashboardData?.total_vehicles || 0}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              {user?.rol === "ADMINISTRADOR" ? "Total en base de datos global" : "Tus vehículos registrados"}
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(21, 62, 117, 0.08)", color: "var(--color-primary)", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Car />
          </div>
        </div>

        {/* KPI 2: Vehículos Activos */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid green" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Vehículos Activos</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "green" }}>
              {dashboardData?.active_vehicles || 0}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              Habilitados con ingreso automático
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(0, 128, 0, 0.08)", color: "green", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.ShieldCheck />
          </div>
        </div>

        {/* KPI 3: Lecturas Hoy */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid #f2a104" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Lecturas (Últimas 24h)</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#f2a104" }}>
              {dashboardData?.today_scans || 0}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              Placas escaneadas hoy en campus
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(242, 161, 4, 0.08)", color: "#f2a104", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Camera />
          </div>
        </div>

        {/* KPI 4: Total Lecturas */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid #722ed1" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Escaneos Históricos</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#722ed1" }}>
              {dashboardData?.total_scans || 0}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              Total acumulado registrado
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(114, 46, 209, 0.08)", color: "#722ed1", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Database />
          </div>
        </div>

        {/* KPI 5: Confianza Promedio */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid #13c2c2" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Confianza OCR Promedio</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#13c2c2" }}>
              {dashboardData?.avg_confidence ? `${(dashboardData.avg_confidence * 100).toFixed(1)}%` : "0.0%"}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              Fiabilidad del motor de lectura
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(19, 194, 194, 0.08)", color: "#13c2c2", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Award />
          </div>
        </div>

        {/* KPI 6: Operadores UAGRM */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid #fa8c16" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Operadores UAGRM</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#fa8c16" }}>
              {dashboardData?.total_users || 0}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              Guardias y administradores
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(250, 140, 22, 0.08)", color: "#fa8c16", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Users />
          </div>
        </div>

        {/* KPI 7: Accesos Registrados */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid #eb2f96" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Accesos Totales</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#eb2f96" }}>
              {accesses.length}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              {accessesByDir[0]?.value || 0} entradas / {accessesByDir[1]?.value || 0} salidas
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(235, 47, 150, 0.08)", color: "#eb2f96", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.ArrowUpDown />
          </div>
        </div>

        {/* KPI 8: Vehículos Dentro */}
        <div className="card" style={{ ...kpiCardBase, borderLeft: "4px solid #096dd9" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p className="eyebrow" style={{ margin: 0 }}>Vehículos Adentro</p>
            <span style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#096dd9" }}>
              {dashboardData?.vehicles_inside || 0}
            </span>
            <p className="muted-text" style={{ fontSize: "0.85rem", margin: 0 }}>
              Dentro del campus en este momento
            </p>
          </div>
          <div style={{ padding: "0.6rem", background: "rgba(9, 109, 217, 0.08)", color: "#096dd9", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Activity />
          </div>
        </div>

      </div>

      {/* Gráficas Integradas con Títulos y Iconos Profesionales */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1.5rem", marginTop: "1.5rem" }}>
        <BarChart
          data={last7}
          labelKey="label"
          valueKey="value"
          title="Escaneos — últimos 7 días"
          icon={<Icons.Calendar />}
          color="#153e75"
        />
        {scansByStatus.length > 0 && (
          <DonutChart segments={scansByStatus} icon={<Icons.Search />} title="Estado de escaneos" />
        )}
        {accesses.length > 0 && (
          <DonutChart segments={accessesByDir} icon={<Icons.Activity />} title="Entradas vs Salidas" />
        )}
      </div>

      {/* Feed de Detecciones Recientes (Original) */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <div className="section-heading" style={{ margin: 0, paddingBottom: "1rem" }}>
          <div>
            <p className="eyebrow">Bitácora en vivo</p>
            <h3 style={{ color: "#153e75" }}>Últimos Escaneos Detectados</h3>
          </div>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid rgba(21, 62, 117, 0.1)", color: "#153e75" }}>
                <th style={{ padding: "0.8rem" }}>Hora / Fecha</th>
                <th style={{ padding: "0.8rem" }}>Placa Detectada</th>
                <th style={{ padding: "0.8rem" }}>Placa Normalizada</th>
                <th style={{ padding: "0.8rem" }}>Confianza</th>
                <th style={{ padding: "0.8rem" }}>Estado</th>
                <th style={{ padding: "0.8rem" }}>Foto</th>
                <th style={{ padding: "0.8rem" }}>BD Vehículo</th>
              </tr>
            </thead>
            <tbody>
              {recentScans.map((s) => (
                <tr key={s.id} style={{ borderBottom: "1px solid rgba(21, 62, 117, 0.05)" }}>
                  <td style={{ padding: "0.5rem 0.8rem" }}>
                    {s.vehicle_photo_id && vehiclePhotoUrls[s.vehicle_photo_id] ? (
                      <img
                        src={vehiclePhotoUrls[s.vehicle_photo_id]}
                        alt={`Vehículo ${s.placa_normalizada || s.placa_detectada || "registrado"}`}
                        title="Foto del vehículo"
                        style={{ width: "44px", height: "44px", borderRadius: "8px", objectFit: "cover", border: "1px solid rgba(21, 62, 117, 0.18)" }}
                      />
                    ) : (
                      <span style={{ color: "#94a3b8" }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: "0.8rem", fontSize: "0.9rem" }}>
                    {new Date(s.creado_el).toLocaleString("es-BO", { timeZone: "America/La_Paz", hour12: false })}
                  </td>
                  <td style={{ padding: "0.8rem", fontFamily: "monospace", fontWeight: "bold" }}>
                    {s.placa_detectada || "N/A"}
                  </td>
                  <td style={{ padding: "0.8rem", fontFamily: "monospace", color: "#153e75", fontWeight: "bold" }}>
                    {s.placa_normalizada || "N/A"}
                  </td>
                  <td style={{ padding: "0.8rem", fontSize: "0.9rem" }}>
                    {s.confianza ? `${(s.confianza * 100).toFixed(1)}%` : "N/A"}
                  </td>
                  <td style={{ padding: "0.8rem" }}>
                    <span style={{
                      padding: "0.2rem 0.4rem",
                      borderRadius: "4px",
                      fontSize: "0.7rem",
                      fontWeight: "bold",
                      background: s.estado === "DETECTADO" ? "#e6ffe6" : s.estado === "BAJA_CONFIANZA" ? "#fff7e6" : "#ffe6e6",
                      color: s.estado === "DETECTADO" ? "green" : s.estado === "BAJA_CONFIANZA" ? "#d46b08" : "#b22234"
                    }}>
                      {s.estado}
                    </span>
                  </td>
                  <td style={{ padding: "0.8rem", fontSize: "0.9rem" }}>
                    {s.has_vehicle ? (
                      <span style={{ color: "green", fontWeight: "bold" }}>✓ En Regla</span>
                    ) : (
                      <span style={{ color: "#b22234", fontWeight: "bold" }}>✗ Desconocido</span>
                    )}
                  </td>
                </tr>
              ))}
              {!recentScans.length && (
                <tr>
                  <td colSpan="7" style={{ padding: "1.5rem", textAlign: "center", color: "#666" }}>
                    No hay escaneos recientes en la bitácora.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Accesos Rápidos */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h3 style={{ color: "#153e75", marginBottom: "1rem" }}>Accesos Rápidos</h3>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          <a href="/subir-placa" className="button" style={{ display: "inline-block", textDecoration: "none", color: "white", padding: "0.6rem 1.2rem", borderRadius: "4px", background: "var(--color-primary)" }}>
            Escanear Placa
          </a>
          <a href="/vehiculos" className="button" style={{ display: "inline-block", textDecoration: "none", color: "white", padding: "0.6rem 1.2rem", borderRadius: "4px", background: "var(--color-primary)" }}>
            {user?.rol === "ADMINISTRADOR" ? "Gestionar Vehículos" : "Mis Vehículos"}
          </a>
          <a href="/accesos" className="button" style={{ display: "inline-block", textDecoration: "none", color: "white", padding: "0.6rem 1.2rem", borderRadius: "4px", background: "var(--color-primary)" }}>
            Control de Accesos
          </a>
          {user?.rol === "ADMINISTRADOR" && (
            <>
              <a href="/usuarios" className="button" style={{ display: "inline-block", textDecoration: "none", color: "white", padding: "0.6rem 1.2rem", borderRadius: "4px", background: "var(--color-primary)" }}>
                Gestionar Usuarios
              </a>
              <a href="/dispositivos" className="button" style={{ display: "inline-block", textDecoration: "none", color: "white", padding: "0.6rem 1.2rem", borderRadius: "4px", background: "var(--color-primary)" }}>
                Gestionar Dispositivos
              </a>
            </>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </section>
  );
}

export default Dashboard;
