import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // dev: cookie-auth API calls hit the FastAPI server directly
      "/api": "http://localhost:8000",
    },
  },
});
