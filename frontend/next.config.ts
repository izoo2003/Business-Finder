import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Django API routes require trailing slashes; do not strip them on Vercel.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
