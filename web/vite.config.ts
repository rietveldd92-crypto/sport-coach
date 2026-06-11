import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// Dev + preview praten tegen de FastAPI-backend op :8000.
const apiProxy = {
  "/api": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "Sport Coach",
        short_name: "Coach",
        description: "Adaptieve trainingscoach — Today & Week",
        lang: "nl",
        start_url: "/",
        display: "standalone",
        background_color: "#0E0F12",
        theme_color: "#0E0F12",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        // Laatste today/week-response offline beschikbaar (UPGRADE_PLAN §6).
        runtimeCaching: [
          {
            urlPattern: ({ url }: { url: URL }) =>
              url.pathname === "/api/today" ||
              url.pathname.startsWith("/api/week/") ||
              url.pathname === "/api/season",
            method: "GET",
            handler: "NetworkFirst",
            options: {
              cacheName: "api-today-week",
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 24, maxAgeSeconds: 60 * 60 * 48 },
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
    }),
  ],
  server: { port: 5173, proxy: apiProxy },
  preview: { port: 4173, proxy: apiProxy },
});
