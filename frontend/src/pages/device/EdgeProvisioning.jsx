import { useState } from "react";
import { provisionEdge } from "../../api/edge";

export default function EdgeProvisioning() {
  const [centralUrl, setCentralUrl] = useState("");
  const [state, setState] = useState({ busy: false, error: "", done: false });

  const submit = async (event) => {
    event.preventDefault();
    setState({ busy: true, error: "", done: false });
    try {
      await provisionEdge({ central_url: centralUrl });
      setState({ busy: false, error: "", done: true });
    } catch (error) {
      setState({ busy: false, done: false, error: error?.response?.data?.detail || "No se pudo completar el aprovisionamiento." });
    }
  };

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "2rem" }}>
      <section className="card" style={{ width: "min(620px, 100%)", padding: "2rem" }}>
        <p style={{ color: "var(--color-secondary)", fontWeight: 700 }}>UAGRM PLATE AGENT</p>
        <h1>Configuración inicial</h1>
        <p>Indica el backend central que validará el primer acceso de cada administrador u operador.</p>
        {state.done ? (
          <div role="status">
            <h2>Backend configurado correctamente</h2>
            <p>Ya puedes iniciar sesión. La primera autenticación en esta PC requiere conexión.</p>
            <a href="/login"><button type="button">Iniciar sesión</button></a>
          </div>
        ) : (
          <form onSubmit={submit} style={{ display: "grid", gap: "1rem" }}>
            <label>URL del backend central<input type="url" required placeholder="https://backend.uagrm.edu.bo" value={centralUrl} onChange={(e) => setCentralUrl(e.target.value)} /></label>
            {state.error && <p role="alert" style={{ color: "var(--color-secondary)" }}>{state.error}</p>}
            <button disabled={state.busy}>{state.busy ? "Guardando..." : "Guardar configuración"}</button>
          </form>
        )}
      </section>
    </main>
  );
}
