import assert from "node:assert/strict";

import { compactMobileMeta, shouldShowWorldSynopsisToggle } from "./world-detail-mobile.ts";

test("compactMobileMeta keeps the first readable genre before separators", () => {
  assert.equal(compactMobileMeta("情感悬疑 / 阵营博弈 / 轻心理恐怖"), "情感悬疑");
});

test("compactMobileMeta truncates long era labels", () => {
  assert.equal(compactMobileMeta("当代（江南老城与湖边茶园）", 8), "当代（江南老城...");
});

test("short world descriptions do not need a synopsis toggle", () => {
  assert.equal(shouldShowWorldSynopsisToggle("一个不断有人失踪的民国小镇。"), false);
});

test("long world descriptions need a synopsis toggle", () => {
  assert.equal(
    shouldShowWorldSynopsisToggle(
      "原创情感悬疑互动世界，背景是江南老城一间表面普通的私房茶室。茶室主人林姨是十年前一场集体家族意外中幸存的遗孀，那场意外导致家族企业崩盘、几位昔日合伙人翻脸。",
    ),
    true,
  );
});
