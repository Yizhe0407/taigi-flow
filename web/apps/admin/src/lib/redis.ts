import { createClient } from "redis";

type RedisClient = ReturnType<typeof createClient>;

const g = globalThis as typeof globalThis & { __adminRedis?: RedisClient };

export function getRedis(): RedisClient {
  if (!g.__adminRedis) {
    const url = process.env.REDIS_URL ?? "redis://localhost:6379";
    g.__adminRedis = createClient({ url });
    g.__adminRedis.on("error", (err) =>
      console.error("[redis]", err.message),
    );
    g.__adminRedis.connect().catch((err: Error) =>
      console.error("[redis] initial connect failed:", err.message),
    );
  }
  return g.__adminRedis;
}
