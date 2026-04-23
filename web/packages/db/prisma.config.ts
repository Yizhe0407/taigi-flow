/// <reference types="node" />

import "dotenv/config";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
    seed: "ts-node prisma/seed.ts",
  },
  datasource: {
    // Keep generate workflows working even when DATABASE_URL is intentionally absent.
    url: process.env.DATABASE_URL ?? "",
  },
});
