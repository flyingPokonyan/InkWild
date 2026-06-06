import assert from "node:assert/strict";

import { isExitIntent } from "./exit-intent.ts";

// 命中：玩家明确的"元游戏"退场短语（整句就是要退出/不玩了/结束游戏）
const SHOULD_DETECT = [
  "退出",
  "退出游戏",
  "我要退出",
  "我要退出游戏",
  "退出吧",
  "不玩了",
  "我不玩了",
  "不想玩了",
  "我不想玩了",
  "不想玩",
  "不想再玩了",
  "结束游戏",
  "结束这局",
  "结束这一局",
  "结束本局",
  "我想结束游戏",
  "不想继续了",
  "关掉游戏",
  "关闭游戏",
  "quit",
  "exit",
  "  退出  ", // 前后空白
  "退出。", // 尾随标点
  "我不玩了！",
];

// 必须放行（别误伤）：剧情内台词 / 叙事 / 跨角色动作，绝不能当成退场
const SHOULD_NOT_DETECT = [
  "", // 空
  "   ", // 纯空白
  "我当众揭穿华妃，扳倒她，结束这场宫斗", // 长叙事，含"结束"但是剧情
  "结束她的性命", // "结束"+宾语，剧情动作
  "结束这场闹剧", // "结束"+非元词
  "我不想再陪你玩了，华妃", // 对 NPC 说的台词（含逗号+人名）
  "我玩够了你们的把戏", // 含"玩"但非元短语
  "她退出了房间", // "退出"嵌在叙事里，非整句意图
  "走吧，我们离开这里", // 离开=剧情，且含标点
  "我要去御花园看看", // 普通行动
  "算了", // 太模糊，不在词典
  "我想结束这场噩梦", // "结束"+剧情宾语
  "继续游戏", // 反向：想继续，绝不能误判成退出
];

for (const text of SHOULD_DETECT) {
  test(`detects exit intent: ${JSON.stringify(text)}`, () => {
    assert.equal(isExitIntent(text), true);
  });
}

for (const text of SHOULD_NOT_DETECT) {
  test(`does NOT misfire on: ${JSON.stringify(text)}`, () => {
    assert.equal(isExitIntent(text), false);
  });
}
