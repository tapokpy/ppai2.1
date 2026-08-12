import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the api service so the same relative fetch
// paths work in both `npm run dev` and the production nginx build (see
// Dockerfile.frontend, which proxies the same /api/ prefix).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
