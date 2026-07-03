import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// GitHub Pages 部署在 lang-drill-agent 仓库子路径下
// 本地构建可设 VITE_BASE_PATH=./ 覆盖；CI 设 /lang-drill-agent/
const base = process.env.VITE_BASE_PATH || "/lang-drill-agent/";

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    target: "es2020",
    cssCodeSplit: true,
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        app: resolve(__dirname, "app.html"),
      },
    },
  },
});
