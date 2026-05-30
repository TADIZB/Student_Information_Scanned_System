import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import basicSsl from "@vitejs/plugin-basic-ssl";


const BACKEND_ROUTES = [
  "/register", "/login", "/logout", "/me", "/auth",
  "/process-scan", "/scan-history",
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
      includeAssets: ["logo.svg"],
      devOptions: { enabled: false },
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
          { src: "logo.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
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