import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Hasil build dilayani engine API di /ui (lihat services/api/app/main.py). Dev: `npm run dev` + engine di :8000.
export default defineConfig({
  base: "/ui/",
  plugins: [vue()],
  build: { outDir: "../api/app/static", emptyOutDir: true, sourcemap: false },
  server: {
    port: 5173,
    proxy: { "/v1": { target: "http://localhost:8000", changeOrigin: true, ws: true } },
  },
});
