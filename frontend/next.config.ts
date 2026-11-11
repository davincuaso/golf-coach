import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
