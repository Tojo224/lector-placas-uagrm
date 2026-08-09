import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [
      react(),
      basicSsl()   // Genera certificado auto-firmado → permite getUserMedia en celular
    ],
    server: {
      port: 5173,
      host: true,   // Escucha en todas las interfaces (WiFi local: 192.168.0.14:5173)
      https: true,  // HTTPS requerido para getUserMedia desde dispositivos móviles
      proxy: {
        "/api": {
          target: env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true
        },
        "/uploads": {
          target: env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true
        },
        "/edge-api": {
          target: env.VITE_EDGE_PROXY_TARGET || "http://127.0.0.1:8765",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/edge-api/, "")
        }
      },
      hmr: {
        protocol: 'wss',
        clientPort: 5173
      }
    }
  };
});
