import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Proxy API/media calls to the FastAPI backend so the browser only ever
  // talks to the Next.js origin (works over LAN, e.g. iPhone Safari hitting
  // http://<mac-lan-ip>:3000, with no cross-origin CORS requests involved).
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" },
      { source: "/outputs/:path*", destination: "http://127.0.0.1:8000/outputs/:path*" },
    ];
  },
};

export default nextConfig;
