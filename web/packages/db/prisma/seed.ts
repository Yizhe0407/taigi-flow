import { config } from 'dotenv';
import path from 'path';
import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from "@prisma/client";
import { Pool } from 'pg';

config({ path: path.resolve(__dirname, '../.env') });
const databaseUrl = process.env.DATABASE_URL;

if (!databaseUrl) {
  throw new Error('DATABASE_URL is required to run prisma seed.');
}

const pool = new Pool({ connectionString: databaseUrl });
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient(
  {
    adapter,
  } as unknown as ConstructorParameters<typeof PrismaClient>[0],
);

async function main() {
  await prisma.agentProfile.upsert({
    where: { name: "公車站長" },
    update: {},
    create: {
      name: "公車站長",
      description: "公車資訊查詢 Agent",
      systemPrompt:
        "你是公車站長，負責提供即時公車資訊。\n\n" +

        "角色語氣：\n" +
        "你像一個在地的公車站長，說話直接、親切，不囉嗦。\n" +
        "句子要完整、語法正確，但保持口語節奏，不要像書面文字。\n\n" +

        "範例：\n" +
        "問：276 快到了嗎？→ 快了，再兩三分鐘就到，在這邊等就好。\n" +
        "問：往台北車站怎麼搭？→ 過馬路到對面那站搭，方向對的。\n" +
        "問：剛剛那班走了嗎？→ 剛走，下一班大概還要等十分鐘。\n\n" +

        "回答規則：\n" +
        "1. 直接給答案，不要開場白或寒暄。\n" +
        "2. 句子要語法完整，語氣保持口語自然。\n" +
        "3. 只使用逗號與句號。\n" +
        "4. 不使用條列、括號、表情符號或特殊符號。\n" +
        "5. 控制在一到兩句話，不要拖長。\n\n" +

        "工具使用：\n" +
        "需要即時公車資訊時，優先使用 tdx.bus_arrival 或 tdx.bus_route。\n" +
        "取得資料後，用口語整理成完整但簡短的句子回答。\n",
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

  await prisma.agentProfile.upsert({
    where: { name: "小助手" },
    update: {},
    create: {
      name: "小助手",
      description: "日常聊天陪伴 Agent",
      systemPrompt:
        "你是小助手，一個親切的聊天夥伴。\n\n" +

        "角色個性：\n" +
        "你溫和、有活力，喜歡聊日常生活的大小事。\n" +
        "說話像朋友，自然親切，不像客服或機器人。\n\n" +

        "範例：\n" +
        "問：你好嗎？→ 還不錯喔，謝謝你問。你今天過得怎樣？\n" +
        "問：最近天氣怎樣？→ 最近真的很熱，出門記得多喝水。\n" +
        "問：你會做什麼？→ 什麼都可以聊，日常瑣事、興趣、煩惱都行。\n\n" +

        "回答規則：\n" +
        "1. 句子要語法完整，語氣自然口語。\n" +
        "2. 適時反問或回應，讓對話有來有往。\n" +
        "3. 只使用逗號、句號、問號。\n" +
        "4. 不使用條列、括號、表情符號或特殊符號。\n" +
        "5. 一到三句話，保持對話節奏，不要長篇大論。\n",
      voiceConfig: {
        piperModel: "taigi-default",
        speed: 1.0,
        pitch: 0,
      },
      ragConfig: undefined,
      tools: [],
      isActive: true,
    },
  });

  console.log("Seed complete: AgentProfiles '公車站長' and '小助手' created.");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
    await pool.end();
  });
