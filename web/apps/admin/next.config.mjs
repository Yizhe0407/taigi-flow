import { config as loadEnv } from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
loadEnv({ path: path.resolve(__dirname, "../../../.env") });

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@taigi-flow/db", "@taigi-flow/types"],
};

export default nextConfig;
