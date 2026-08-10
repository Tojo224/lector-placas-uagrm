import axios from "axios";

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

export { edgeBaseURL, isEdgeHosted };
