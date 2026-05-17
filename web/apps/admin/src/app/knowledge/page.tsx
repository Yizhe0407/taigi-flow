import { prisma } from "@taigi-flow/db";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const profiles = await prisma.agentProfile.findMany({
    orderBy: { name: "asc" },
    select: { id: true, name: true, ragConfig: true },
  });

  const counts = await Promise.all(
    profiles.map((p) =>
      prisma.$queryRaw<[{ count: bigint }]>`
        SELECT COUNT(*)::bigint AS count FROM "KnowledgeChunk" WHERE "collectionId" = ${p.id}
      `.then((r) => Number(r[0].count))
    )
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">知識庫</h1>
      <p className="text-sm text-gray-500 mb-4">
        每個 Agent 人格對應一個知識庫（collection），collection ID = Agent Profile ID。
      </p>

      <div className="space-y-3">
        {profiles.map((p, i) => {
          const rag = p.ragConfig as { enabled?: boolean } | null;
          return (
            <div
              key={p.id}
              className="flex items-center justify-between border border-border rounded-lg px-4 py-3 bg-white"
            >
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-gray-400 mt-0.5">{p.id}</div>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-500">{counts[i]} chunks</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    rag?.enabled
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-500"
                  }`}
                >
                  {rag?.enabled ? "RAG 啟用" : "RAG 停用"}
                </span>
                <Link
                  href={`/knowledge/${p.id}`}
                  className="text-sm text-blue-600 hover:underline"
                >
                  管理
                </Link>
              </div>
            </div>
          );
        })}
        {profiles.length === 0 && (
          <p className="text-gray-400 text-sm">尚無 Agent 人格。請先在「Agent 人格」頁面建立。</p>
        )}
      </div>
    </div>
  );
}
