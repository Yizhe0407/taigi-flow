const _LABEL = new TextEncoder().encode("admin-session-v1");

/** Derive a fixed opaque token from the secret. Works in Edge + Node (Web Crypto). */
export async function deriveAdminToken(secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, _LABEL);
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
