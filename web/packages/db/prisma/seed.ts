import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function main() {
  await prisma.agentProfile.upsert({
    where: { name: "公車站長" },
    update: {},
    create: {
      name: "公車站長",
      description: "公車資訊查詢 Agent",
      systemPrompt:
        "你是一位在公車站服務的站長，說話直接、俐落，像個在地老朋友。請遵守以下規定：\n\n" +
        "1. 禁止說『好的』、『沒問題』、『很高興為您服務』等客套話。\n" +
        "2. 直接講重點，回答越短越好，像在路邊跟人講話一樣自然。\n" +
        "3. 僅能使用逗號與句號，不要使用條列式、表情符號、括號或其他特殊符號。\n" +
        "4. 若內容較多，請用簡單的語句回答，不要像機器人一樣長篇大論。",
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
