import axios from "axios";
import { clearSession } from "../services/storage";

// Timeout generoso para endpoints de análisis OCR en CPU.
const OCR_TIMEOUT = 120_000; // 2 minutos
const DEFAULT_TIMEOUT = 30_000; // 30 segundos para el resto de peticiones

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: DEFAULT_TIMEOUT,
  withCredentials: true,
  headers: {
    "X-Requested-With": "XMLHttpRequest"
  }
});

apiClient.interceptors.request.use((config) => {
  if (config.url?.includes("/plates/analyze")) {
    config.timeout = OCR_TIMEOUT;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearSession();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;
