import axios from "axios";
import apiClient from "./axios";

const isLoopback = ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
const isEdgeHosted = isLoopback && window.location.port !== "5173";
const configuredBase = import.meta.env.VITE_EDGE_API_BASE_URL;
const edgeBaseURL = configuredBase || (
  import.meta.env.DEV
    ? "/edge-api/api/v1/edge"
    : isEdgeHosted
      ? `${window.location.origin}/api/v1/edge`
      : "http://127.0.0.1:8765/api/v1/edge"
);

export const edgeApiClient = axios.create({
  baseURL: edgeBaseURL,
  timeout: 120_000,
  withCredentials: false
});

edgeApiClient.interceptors.request.use((config) => {
  const session = readSession();
  if (session?.token) {
    config.headers.Authorization = `Bearer ${session.token}`;
  }
  return config;
});

export async function analyzeWithEdge(
  formData,
  realtime = false,
  signal = undefined,
  confirm = true
) {
  const { data } = await edgeApiClient.post("/analyze", formData, {
    params: { realtime, confirm },
    headers: { "Content-Type": "multipart/form-data" },
    signal
  });
  return data;
}

export async function getEdgeHealth() {
  const { data } = await edgeApiClient.get("/health", { timeout: 4_000 });
  return data;
}

export async function getEdgeStatus() {
  const { data } = await edgeApiClient.get("/status", { timeout: 4_000 });
  return data;
}

export async function getEdgeVersion() {
  const { data } = await edgeApiClient.get("/version", { timeout: 4_000 });
  return data;
}

export async function provisionEdge(payload) {
  const { data } = await edgeApiClient.post("/provision", payload, { timeout: 30_000 });
  return data;
}

export async function uploadPlateImage(formData, realtime = false, signal = undefined) {
  const endpoint = realtime ? "/v1/plates/analyze?realtime=true" : "/v1/plates/analyze";
  const { data } = await apiClient.post(endpoint, formData, {
    headers: {
      "Content-Type": "multipart/form-data"
    },
    signal
  });
  return data;
}

export { edgeBaseURL, isEdgeHosted };
