import { useState } from "react";
import { provisionEdge } from "../../api/edge";

export default function EdgeProvisioning() {
  const [form, setForm] = useState({ central_url: "", device_id: "", device_key: "" });
  const [state, setState] = useState({ busy: false, error: "", done: false });

  const submit = async (event) => {
    event.preventDefault();
    setState({ busy: true, error: "", done: false });
    try {
      await provisionEdge(form);
      setForm((current) => ({ ...current, device_key: "" }));
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
        <p>Conecta esta instalación con el dispositivo creado por un administrador. La clave se protege con Windows DPAPI y no volverá a mostrarse.</p>
        {state.done ? (
          <div role="status">
            <h2>Instalación provisionada correctamente</h2>
            <p>El snapshot operativo fue descargado y la sincronización ya puede comenzar.</p>
            <a href="/subir-placa"><button type="button">Abrir scanner</button></a>
          </div>
        ) : (
          <form onSubmit={submit} style={{ display: "grid", gap: "1rem" }}>
            <label>URL del backend central<input type="url" required placeholder="https://backend.uagrm.edu.bo" value={form.central_url} onChange={(e) => setForm({ ...form, central_url: e.target.value })} /></label>
            <label>ID del dispositivo<input required autoComplete="off" value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })} /></label>
            <label>Clave Edge<input type="password" required autoComplete="new-password" value={form.device_key} onChange={(e) => setForm({ ...form, device_key: e.target.value })} /></label>
            {state.error && <p role="alert" style={{ color: "var(--color-secondary)" }}>{state.error}</p>}
            <button disabled={state.busy}>{state.busy ? "Validando y descargando snapshot..." : "Aprovisionar instalación"}</button>
          </form>
        )}
      </section>
    </main>
  );
}
