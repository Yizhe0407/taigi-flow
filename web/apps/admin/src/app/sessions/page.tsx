import { prisma } from "@taigi-flow/db";
import { PageHeader } from "@/components/page-header";
import SessionsTable from "./_components/SessionsTable";

export const dynamic = "force-dynamic";

export default async function SessionsPage() {
  const agents = await prisma.agentProfile.findMany({
    select: { id: true, name: true },
    orderBy: { name: "asc" },
  });

  return (
    <div>
      <PageHeader title="對話日誌" description="查看所有使用者與 Agent 的對話紀錄" />
      <SessionsTable agents={agents} />
    </div>
  );
}
