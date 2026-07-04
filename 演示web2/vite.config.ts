import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// GitHub Pages 部署在 lang-drill-agent 仓库子路径下
// 本地构建可设 VITE_BASE_PATH=./ 覆盖；CI 设 /lang-drill-agent/
const base = process.env.VITE_BASE_PATH || "/lang-drill-agent/";

export default defineConfig({
  base,
  plugins: [
    react(),
    // 修正 mock/App.tsx 中硬编码的 /assets/ 绝对路径：替换为相对路径
    // 让 iframe 内的图片从 base 路径解析（app.html 在 base 下，相对路径会正确解析）
    {
      name: "rewrite-mock-asset-paths",
      enforce: "pre",
      transform(code: string, id: string) {
        if (id.includes("mock") && /App\.tsx$/.test(id)) {
          return code.replace(/src="\/assets\//g, 'src="./assets/');
        }
        return null;
      },
    },
  ],
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
