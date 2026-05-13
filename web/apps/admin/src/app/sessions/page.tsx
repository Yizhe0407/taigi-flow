import { prisma } from "@taigi-flow/db";
import Link from "next/link";

export const dynamic = "force-dynamic";

// Sessions without endedAt but older than this are considered stale (not truly active).
const STALE_THRESHOLD_MS = 2 * 60 * 60 * 1000; // 2 hours

function sessionStatus(s: { endedAt: Date | null; startedAt: Date }) {
  if (s.endedAt) return "ended";
  const age = Date.now() - new Date(s.startedAt).getTime();
  return age > STALE_THRESHOLD_MS ? "stale" : "active";
}

export default async function SessionsPage() {
  const sessions = await prisma.session.findMany({
    orderBy: { startedAt: "desc" },
    take: 100,
    include: {
      agentProfile: { select: { name: true } },
      _count: { select: { logs: true } },
    },
  });

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">對話日誌</h1>

      {sessions.length === 0 && (
        <p className="text-gray-500 text-sm">尚無對話紀錄。</p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
              <th className="py-2 pr-4 font-medium">時間</th>
              <th className="py-2 pr-4 font-medium">Agent</th>
              <th className="py-2 pr-4 font-medium">房間</th>
              <th className="py-2 pr-4 font-medium">輪次</th>
              <th className="py-2 font-medium">狀態</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const status = sessionStatus(s);
              return (
                <tr
                  key={s.id}
                  className="border-b border-gray-100 hover:bg-gray-50"
                >
                  <td className="py-2 pr-4 whitespace-nowrap text-gray-600">
                    {new Date(s.startedAt).toLocaleString("zh-TW", {
                      timeZone: "Asia/Taipei",
                    })}
                  </td>
                  <td className="py-2 pr-4">{s.agentProfile.name}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-gray-500">
                    {s.livekitRoom}
                  </td>
                  <td className="py-2 pr-4">{s._count.logs}</td>
                  <td className="py-2">
                    {status === "active" && (
                      <span className="text-xs text-green-600">進行中</span>
                    )}
                    {status === "ended" && (
                      <span className="text-xs text-gray-400">已結束</span>
                    )}
                    {status === "stale" && (
                      <span
                        title="Worker 未正常結束（SIGKILL / 崩潰）"
                        className="text-xs text-amber-500 cursor-help"
                      >
                        未正常結束
                      </span>
                    )}
                    <Link
                      href={`/sessions/${s.id}`}
                      className="ml-3 text-xs text-indigo-600 hover:underline"
                    >
                      查看
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
