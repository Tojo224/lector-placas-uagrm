import axios from "axios";
import { readSession } from "../services/storage";

// Timeout generoso para endpoints de análisis OCR en CPU.
const OCR_TIMEOUT = 120_000; // 2 minutos
const DEFAULT_TIMEOUT = 30_000; // 30 segundos para el resto de peticiones

export const centralApiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: DEFAULT_TIMEOUT,
  withCredentials: true,
  headers: {
    "X-Requested-With": "XMLHttpRequest"
  }
});

centralApiClient.interceptors.request.use((config) => {
  // Rutas de análisis de imagen necesitan más tiempo
  if (config.url?.includes("/plates/analyze")) {
    config.timeout = OCR_TIMEOUT;
  }
  
  // Añadir token de autorización si existe en la sesión guardada
  const session = readSession();
  if (session?.token) {
    config.headers.Authorization = `Bearer ${session.token}`;
  }
  return config;
});

export default centralApiClient;
