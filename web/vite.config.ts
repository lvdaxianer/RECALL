import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(fileURLToPath(new URL(".", import.meta.url)), "./src"),
    },
  },
  server: {
    // 反代 /api 到后端（开发用，HMR/WebSocket 走 vite 默认端口）
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        // SSE 流式接口需要禁用缓冲
        changeOrigin: true,
        ws: true,
      },
    },
    // HMR 通信端口（与 vite 主端口同端口）
    hmr: {
      overlay: true,
      clientPort: 5173,
    },
    // 优化热更新：排除不需要监控的目录
    watch: {
      ignored: [
        "**/node_modules/**",
        "**/dist/**",
        "**/.git/**",
        // 排除后端目录（避免 vite 误监控导致重载抖动）
        "../app/**",
        "../scripts/**",
        "../tests/**",
        "../data/**",
      ],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
