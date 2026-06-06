<!--
  InkWild PR 模板
  视觉/前端 PR 必须填完 §视觉自检表，全部打勾才能合。
  规范：docs/visual-principles.md v2.1 / docs/cover-art-spec.md v1.1
-->

## 改了什么

<!-- 一两句话写清楚 what + why。"why" 最关键——commit message 不重要的，PR 描述重要 -->

## 测试

<!-- 跑了什么、看了什么、回归了什么 -->

- [ ] 本地起前端 / 后端跑通了
- [ ] 改的页面在 1280px 桌面 + 375px 移动端都看过
- [ ] 关键路径手测（golden path + 1-2 个边角 case）

---

## 视觉自检表（前端 PR 必填，对照 visual-principles.md v2.1）

> 不是前端改动？删掉这一节。

```
[ ] 字号只用了 7 档之一（display 64 / h1 32 / h2 20 / narrative 16 / body 15 / meta 12 / caps 11）
[ ] 一屏字号 ≤ 3 档（§1.3）
[ ] serif 仅用于 hero / 卡片标题 / 引文 / 游戏页叙事（§1.1）
[ ] mono 仅用于数字 / 时间戳 / 版本号（§1.1）
[ ] 装饰性 accent 一屏 ≤ 1 处，且是暖金 --lv-accent（§2.1）
[ ] 绿色 --lv-accent-2 仅用于"自由模式"语义编码（§2.1）
[ ] 圆角只用了 16 (--lv-r-card) / 10 (--lv-r-input，仅表单) / 9999 (--lv-r-pill)（§3）
[ ] 间距用 9 档之一，没出现 7/10/14/18/22/28（§4）
[ ] z-index 用 6 档之一（base/sticky/drawer/modal/toast/overlay），没出现 99/999/9999（§5）
[ ] hover/transition ≤ 250ms，cinematic 例外仅首页 hero 和游戏结局（§6）
[ ] 卡片信息项 ≤ 5（§7.1）
[ ] 没有"翻阅你的足印"类堆叠修饰文案（§9.1）
[ ] 没有四字 serif 大标题占满首屏（§8.4，首页 hero 例外）
[ ] toolbar 左对齐（§8.1）
[ ] 加载态不写"正在加载..."文字，用 .lv-loading-pulse（§10.1）
[ ] 焦点环可见、对比度 ≥ 4.5:1（§13）
[ ] prefers-reduced-motion 时关闭长动效（§6 §13）
```

## 引擎/后端自检（后端 PR 必填）

> 不是后端改动？删掉这一节。

- [ ] 全链路 async，无同步阻塞
- [ ] schema 放 `schemas/`，response 包 `{code, data, message}`
- [ ] 修改 session 状态的接口加了 `SessionLock`
- [ ] SSE payload 带 `version: 1`，没有把 `state_ready` 内部事件发给前端
- [ ] 用 `structlog` 不用 `print()`
- [ ] LLM 调用走 LLMRouter，没有硬编码 provider/model 名

## 其他

<!-- 截图、链接、关联 issue -->
