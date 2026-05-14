import { prisma } from "@taigi-flow/db";
import { notFound } from "next/navigation";
import TurnTable from "./_components/TurnTable";

export const dynamic = "force-dynamic";

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await prisma.session.findUnique({
    where: { id },
    include: { agentProfile: { select: { name: true } } },
  });
  if (!session) notFound();

  const turns = await prisma.interactionLog.findMany({
    where: { sessionId: id },
    orderBy: { turnIndex: "asc" },
  });

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-2xl font-bold">Session 詳情</h1>
        <p className="text-sm text-gray-500 mt-1">
          Agent: {session.agentProfile.name} ·{" "}
          {new Date(session.startedAt).toLocaleString("zh-TW", {
            timeZone: "Asia/Taipei",
          })}
        </p>
      </div>
      <TurnTable turns={turns} />
    </div>
  );
}
