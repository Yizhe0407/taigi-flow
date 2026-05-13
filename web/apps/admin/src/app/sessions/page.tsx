import { prisma } from "@taigi-flow/db";
import SessionsTable from "./_components/SessionsTable";

export const dynamic = "force-dynamic";

export default async function SessionsPage() {
  const agents = await prisma.agentProfile.findMany({
    select: { id: true, name: true },
    orderBy: { name: "asc" },
  });

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">對話日誌</h1>
      <SessionsTable agents={agents} />
    </div>
  );
}
