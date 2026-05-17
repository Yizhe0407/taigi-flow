import { config as loadEnv } from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");
loadEnv({ path: path.resolve(repoRoot, ".env") });

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@taigi-flow/db", "@taigi-flow/types"],
  experimental: {
    outputFileTracingRoot: repoRoot,
  },
};

export default nextConfig;
