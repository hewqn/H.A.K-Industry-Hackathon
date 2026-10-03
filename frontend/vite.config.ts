import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy relative API calls locally. Deployment must supply the same-origin API path.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  // TODO(FRONTEND): add chunk boundaries when the engineer viewer and voice SDK are integrated.
});
