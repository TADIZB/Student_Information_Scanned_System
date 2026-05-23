import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import basicSsl from "@vitejs/plugin-basic-ssl";

// Các route của backend — proxy qua Vite để tránh mixed-content khi dùng HTTPS
const BACKEND_ROUTES = [
  "/register", "/login", "/logout", "/me", "/auth",
  "/process-scan", "/scan-history", "/export-card",
  "/students", "/files", "/images",
];

const backendProxy = Object.fromEntries(
  BACKEND_ROUTES.map((route) => [
    route,
    { target: "http://localhost:8000", changeOrigin: true },
  ])
);

export default defineConfig({
  plugins: [
    basicSsl(),
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      devOptions: { enabled: true },   // bật service worker trong dev mode
      manifest: {
        name: "TADIZB Scanner",
        short_name: "TADIZB",
        description: "Quét và tra cứu thẻ sinh viên",
        theme_color: "#dc2626",
        background_color: "#ffffff",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,woff2}"],
        navigateFallback: "/",
      },
    }),
  ],
  server: {
    port: 3000,
    open: true,
    host: true,
    https: true,
    proxy: backendProxy,
  },
  build: {
    outDir: "dist",
  },
});