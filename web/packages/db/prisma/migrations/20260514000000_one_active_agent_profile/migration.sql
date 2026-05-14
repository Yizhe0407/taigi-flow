-- Enforce that at most one AgentProfile may have isActive = true at any time.
-- Backstop for the application-layer exclusive-activation logic, which was
-- inconsistently enforced (PUT had it, POST and seed didn't).

-- Step 1: clean up any pre-existing duplicate-active rows by keeping only the
-- most-recently-updated active profile and deactivating the rest.
UPDATE "AgentProfile"
SET "isActive" = false
WHERE "id" NOT IN (
  SELECT "id" FROM "AgentProfile"
  WHERE "isActive" = true
  ORDER BY "updatedAt" DESC
  LIMIT 1
)
AND "isActive" = true;

-- Step 2: partial unique index — only rows with isActive = true must be unique.
-- Since all such rows have the same value (true), at most one can exist.
CREATE UNIQUE INDEX "one_active_agent_profile"
  ON "AgentProfile" ("isActive")
  WHERE "isActive" = true;
