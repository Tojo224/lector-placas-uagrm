import apiClient from "./axios";

function mapAuthError(error, fallbackMessage) {
  if (error?.response?.data?.detail) {
    const detail = error.response.data.detail;
    if (typeof detail === "string") {
      throw new Error(detail);
    } else if (Array.isArray(detail)) {
      const msg = detail.map((d) => {
        let field = d.loc ? d.loc[d.loc.length - 1] : "campo";
        let message = d.msg || "Valor inválido";
        
        // Translate common field names
        const fieldTranslations = {
          nombre: "El nombre",
          apellido_paterno: "El apellido paterno",
          apellido_materno: "El apellido materno",
          carnet: "El carnet de identidad (CI)",
          contrasena: "La contraseña",
          rol: "El rol"
        };
        const friendlyField = fieldTranslations[field] || field;

        // Clean up and translate common Pydantic error messages
        if (message.startsWith("String should have at least")) {
          const match = message.match(/\d+/);
          const num = match ? match[0] : "8";
          return `${friendlyField} debe tener al menos ${num} caracteres.`;
        }
        if (message.startsWith("Value error, ")) {
          return message.replace("Value error, ", "");
        }
        if (message === "Field required") {
          return `${friendlyField} es obligatorio.`;
        }
        return `${friendlyField}: ${message}`;
      }).join(" ");
      throw new Error(msg);
    } else {
      throw new Error(JSON.stringify(detail));
    }
  }

  if (!error?.response) {
    throw new Error("No se pudo conectar con el backend. Verifica que FastAPI este encendido en el puerto 8000 o 8010.");
  }

  if (error?.code === "ECONNABORTED") {
    throw new Error("El servidor tardo demasiado en responder.");
  }

  if (error?.message === "Network Error") {
    throw new Error("No se pudo conectar con el backend. Verifica que FastAPI este encendido.");
  }

  throw new Error(fallbackMessage);
}

function normalizeSession(data) {
  if (data?.user) {
    return { user: data.user };
  }

  throw new Error("El servidor devolvió una respuesta de autenticación inválida. Contacta al administrador.");
}

export async function loginUser(credentials) {
  try {
    const { data } = await apiClient.post("/auth/login", credentials);
    return normalizeSession(data);
  } catch (error) {
    mapAuthError(error, "No se pudo iniciar sesion.");
  }
}

export async function registerUser(payload) {
  try {
    const { data } = await apiClient.post("/auth/register", payload);
    return normalizeSession(data);
  } catch (error) {
    mapAuthError(error, "No se pudo completar el registro.");
  }
}

export async function getProfile() {
  try {
    const { data } = await apiClient.get("/auth/me");
    return data;
  } catch (error) {
    mapAuthError(error, "No se pudo cargar el perfil.");
  }
}

export async function updateProfile(payload) {
  try {
    const { data } = await apiClient.put("/auth/me", payload);
    return data;
  } catch (error) {
    mapAuthError(error, "No se pudo actualizar el perfil.");
  }
}

export async function deleteProfile() {
  try {
    await apiClient.delete("/auth/me");
    return true;
  } catch (error) {
    mapAuthError(error, "No se pudo eliminar el perfil.");
  }
}

export async function uploadProfilePhoto(userId, file) {
  try {
    const form = new FormData();
    form.append("file", file);
    const { data } = await apiClient.post(`/v1/media/users/${userId}/photo`, form);
    return data;
  } catch (error) {
    mapAuthError(error, "No se pudo subir la foto de perfil.");
  }
}

export async function deleteProfilePhoto(userId) {
  try {
    await apiClient.delete(`/v1/media/users/${userId}/photo`);
  } catch (error) {
    mapAuthError(error, "No se pudo eliminar la foto de perfil.");
  }
}

export async function getMediaUrl(mediaId) {
  try {
    const { data } = await apiClient.get(`/v1/media/${mediaId}/url`);
    return data;
  } catch (error) {
    mapAuthError(error, "No se pudo obtener la URL del archivo.");
  }
}

export async function logoutUser() {
  try {
    await apiClient.post("/auth/logout");
  } catch (error) {
    console.warn("Error al hacer logout en el backend:", error);
  }
  return true;
}

// Funciones de administración para usuarios
export async function listUsers() {
  try {
    const { data } = await apiClient.get("/auth/users");
    return data;
  } catch (error) {
    mapAuthError(error, "No se pudo cargar la lista de usuarios.");
  }
}

export async function updateUserByAdmin(userId, payload) {
  try {
    const { data } = await apiClient.put(`/auth/users/${userId}`, payload);
    return data;
  } catch (error) {
    mapAuthError(error, "No se pudo actualizar el usuario.");
  }
}

export async function deleteUserByAdmin(userId) {
  try {
    await apiClient.delete(`/auth/users/${userId}`);
    return true;
  } catch (error) {
    mapAuthError(error, "No se pudo eliminar el usuario.");
  }
}
