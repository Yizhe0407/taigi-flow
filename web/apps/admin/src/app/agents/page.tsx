import { prisma } from "@taigi-flow/db";
import AgentList from "./_components/AgentList";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const profiles = await prisma.agentProfile.findMany({
    orderBy: { createdAt: "desc" },
  });
  return <AgentList initial={profiles} />;
}
