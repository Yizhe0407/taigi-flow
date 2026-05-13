import { prisma } from "@taigi-flow/db";
import { notFound } from "next/navigation";
import AgentForm from "../_components/AgentForm";

export const dynamic = "force-dynamic";

export default async function EditAgentPage({ params }: { params: { id: string } }) {
  const profile = await prisma.agentProfile.findUnique({ where: { id: params.id } });
  if (!profile) notFound();
  return <AgentForm profile={profile} />;
}
