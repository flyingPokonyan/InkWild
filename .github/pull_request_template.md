<!--
  InkWild PR 模板
  前端 PR 过一遍下面的视觉自检（参考，不是逐条卡死）。
  参考：frontend/AGENTS.md（前端唯一参考）/ docs/design/cover-art-spec.md（生图）
-->

## 改了什么

<!-- 一两句话写清楚 what + why。"why" 最关键——commit message 不重要的，PR 描述重要 -->

## 测试

<!-- 跑了什么、看了什么、回归了什么 -->

- [ ] 本地起前端 / 后端跑通了
- [ ] 改的页面在 1280px 桌面 + 375px 移动端都看过
- [ ] 关键路径手测（golden path + 1-2 个边角 case）

---

## 视觉自检（前端 PR，参考 frontend/AGENTS.md）

> 不是前端改动？删掉这一节。参考，不是逐条卡死——拿不准看 `globals.css` 与现成组件。

```
[ ] 字号用 .lv-t-* 工具类，没写 text-[Xrem] / inline fontSize 数字
[ ] 颜色用 var(--lv-*)，没引旧 token（--font-size-* / --ta-* / --color-accent）
[ ] 金色当语义色用（品牌/active/spotlight/focus），没拿来 hover 描金 / 装饰
[ ] 圆角 / 间距 / z-index 用 globals 里的 token，没硬编码任意值
[ ] 动效常规 ≤ 200ms，cinematic 长动效仅 hero / 游戏结局
[ ] 加载态用 Branch pulse，不写"正在加载…"；错误态红字配文字或图标
[ ] 同类组件复用现成的（卡片 / chip / 按钮），没每页重画一套
[ ] 375px 单手可用，触摸目标 ≥ 44px，不依赖 hover 表达状态
[ ] 焦点环可见、对比度够；prefers-reduced-motion 降级长动效
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
