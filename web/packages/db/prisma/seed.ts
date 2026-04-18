import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function main() {
  await prisma.agentProfile.upsert({
    where: { name: "公車站長" },
    update: {},
    create: {
      name: "公車站長",
      description: "台語公車資訊查詢 Agent",
      systemPrompt:
        "你是一個熱心的公車站長，用台語回答乘客關於公車路線、到站時間的問題。回答簡潔清楚。",
      voiceConfig: {
        piperModel: "taigi-default",
        speed: 1.0,
        pitch: 0,
      },
      ragConfig: undefined,
      tools: ["tdx.bus_arrival", "tdx.bus_route"],
      isActive: true,
    },
  });

  console.log("Seed complete: AgentProfile '公車站長' created.");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
