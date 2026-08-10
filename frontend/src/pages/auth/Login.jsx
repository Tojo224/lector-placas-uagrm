import { useState } from "react";
import { Navigate } from "react-router-dom";

import Loader from "../../components/Loader";
import { useAuth } from "../../hooks/useAuth";
import { isEdgeHosted } from "../../api/edge";

function Login() {
  const { user, authLoading, signInLoading, signIn } = useAuth();
  const [formData, setFormData] = useState({
    carnet: "",
    contrasena: ""
  });
  const [error, setError] = useState("");

  if (authLoading) {
    return (
      <main className="auth-screen">
        <Loader label="Verificando sesión..." />
      </main>
    );
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");

    try {
      await signIn(formData);
    } catch (submitError) {
      setError(submitError.message || "No se pudo iniciar sesión.");
      console.error(submitError);
    }
  };

  return (
    <main className="auth-screen auth-screen-simple">
      <form className="card auth-card auth-card-compact" onSubmit={handleSubmit}>
        <div>
          <p className="eyebrow">SIARP</p>
          <h2>Iniciar sesión</h2>
          <p className="muted-text">
            Ingresa tu Registro / Carnet de Identidad y contraseña para acceder.
          </p>
        </div>

        <label className="field-group">
          <span>Registro / Carnet de Identidad</span>
          <input
            type="text"
            placeholder="202400123"
            value={formData.carnet}
            onChange={(event) =>
              setFormData((current) => ({
                ...current,
                carnet: event.target.value
              }))
            }
            required
          />
        </label>

        <label className="field-group">
          <span>Contraseña</span>
          <input
            type="password"
            placeholder="Ingresa tu contraseña"
            value={formData.contrasena}
            onChange={(event) =>
              setFormData((current) => ({
                ...current,
                contrasena: event.target.value
              }))
            }
            required
          />
        </label>

        {error && <p className="error-text">{error}</p>}

        <button type="submit" disabled={signInLoading}>
          {signInLoading ? "Ingresando..." : "Entrar al sistema"}
        </button>

        <p className="helper-text">
          {isEdgeHosted
            ? <>La primera autenticación en esta PC requiere Internet. <a href="/configuracion">Configurar backend</a>.</>
            : <>¿No tienes cuenta? </>}
        </p>
      </form>
    </main>
  );
}

export default Login;
