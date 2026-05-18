import { prisma } from "@taigi-flow/db";
import { notFound } from "next/navigation";
import RefreshButton from "./_components/RefreshButton";
import TurnTable from "./_components/TurnTable";

export const dynamic = "force-dynamic";

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const TURN_LIMIT = 500;
  const [session, turns, totalTurns] = await Promise.all([
    prisma.session.findUnique({
      where: { id },
      include: { agentProfile: { select: { name: true } } },
    }),
    prisma.interactionLog.findMany({
      where: { sessionId: id },
      orderBy: { turnIndex: "asc" },
      take: TURN_LIMIT,
      select: {
        id: true,
        turnIndex: true,
        userAsrText: true,
        llmRawText: true,
        hanloText: true,
        taibunText: true,
        latencyFirstAudio: true,
        latencyTotal: true,
        wasBargedIn: true,
        errorFlag: true,
      },
    }),
    prisma.interactionLog.count({ where: { sessionId: id } }),
  ]);
  if (!session) notFound();

  return (
    <div>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">Session 詳情</h1>
          <p className="text-sm text-gray-500 mt-1">
            Agent: {session.agentProfile.name} ·{" "}
            {new Date(session.startedAt).toLocaleString("zh-TW", {
              timeZone: "Asia/Taipei",
            })}
            {" "}· {totalTurns} 輪{turns.length < totalTurns ? `（顯示前 ${turns.length}）` : ""}
          </p>
        </div>
        <RefreshButton />
      </div>
      <TurnTable turns={turns} totalCount={totalTurns} />
    </div>
  );
}
