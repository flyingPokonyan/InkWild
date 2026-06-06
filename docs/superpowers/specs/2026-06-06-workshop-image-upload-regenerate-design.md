# 草稿页图片「上传 + 重抽」设计

> 创建于 2026-06-06。状态：设计已确认，待出实现计划。

## 背景与问题

创作工坊的草稿编辑器（世界 / 剧本）里，图片由 AI 在生成阶段产出（Seedream，经 `image_storage` 落 OSS）。但编辑器对图片几乎没有补救手段：

| 图 | 当前处置 |
|---|---|
| 世界 `hero_image`（21:9）| 纯展示（`CoverDeck`），**零编辑入口** |
| 世界 `cover_image`（3:2）| 纯展示，**零编辑入口** |
| 剧本 `cover_image`（3:2）| 纯展示（`CoverFrame`），**零编辑入口** |
| 角色 `avatar`（每世界 N 个，可能 10+）| 仅一个 URL 文本框，需手动粘链接 |

真实痛点：AI 配图偶尔翻车（兜底占位图 / 风格不对 / IP 角色长歪），创作者在草稿页无从补救——三张封面甚至完全改不了。

## 目标

给草稿页所有图片两种纠错能力：

1. **手动上传**——永远能用的逃生口（"我有更好的图"）。
2. **重新生成（重抽）**——单张图重生，可填补充方向（"我没图，想换一张"）。这是多数创作者真正想要的。

覆盖全部四类图：世界 hero、世界 cover、剧本 cover、角色 avatar。

## 非目标（YAGNI）

- 不做手动裁剪框（`image_cropper` 已存在，留作以后；v1 上传图用 `object-fit: cover` + 比例提示）。
- 不暴露完整 prompt 给用户编辑（只给"补充方向"一句话）。
- 重抽不走 SSE 异步任务链路（那是整世界生成才需要的重型流程）。

## 关键决策（已拍板）

| 点 | 决策 | 理由 |
|---|---|---|
| 范围 | 上传 + 重抽都做，覆盖四类图 | 两者互补，缺一不可 |
| 重抽控制力 | 一键重抽 + 可填**补充方向**（一句话，可选） | 给控制力但不暴露 prompt 内部 |
| 重抽同步性 | **同步 POST + 转圈** | 单张图几秒，异步是 overkill |
| 上传体积上限 | 头像 2MB / 封面 5MB | 封面分辨率高 |
| 重抽计费 | **v1 不计费**（见下「计费现状」）；图像走 metered 槽但缺 task/session 锚无法落 token_usage | 完整计费需为单图重抽挂 task 行，留作 follow-up |
| 上传传输 | base64 data URL（JSON），**不引 multipart** | 复用已验证的头像上传模式 |

## UI 设计

核心原则：**上传/重抽是低频纠错动作，不该常驻污染编辑器**。静息态保持现在的干净电影感，复杂度只在用户主动要改某张图时才出现。

### 一个统一控件 `<ImageField>`，按框尺寸自适应

四类图共用同一控件、同一动作模型，仅尺寸/形状不同（封面矩形框、头像圆形缩览）。

**静息态 = 与现状一致**：封面仍是干净展示框 + caps 标签；头像仍是缩览。唯一新增是图片角落一个**极克制、常驻**的小入口图标（✎/⋯）——常驻是为了可发现性（移动端没 hover），但视觉上极轻。封面此前压根没有编辑入口，加一个小角标是净赚。

**动作层（点角标 / 点整张图唤出）**：
- 桌面端：**Radix Popover**（`@radix-ui/react-popover` 已装，项目首次使用），锚定在图上。
- 移动端：复用 **`MobileSheet`（vaul）**（`components/ui/MobileSheet.tsx`）。
- 内容（两端一致）：当前图缩览 + 三个动作
  - `⤓ 上传本地图片`
  - `↻ 重新生成` —— 点开后就地展开"补充方向（可选）"输入 + 「开始重抽」
  - `🔗 粘贴链接` —— 保留现有 URL 入口，降级为次要项

动作层是独立浮层，重抽方向输入在浮层内，**不 inline 撑爆页面、无 reflow**。

### 各处落点

- 世界 hero / cover：在 `CoverDeck` / `CoverFrame` 的图框上挂角标，复用同一 `<ImageField>`。
- 剧本 cover：同上（`CoverFrame`）。
- 角色 avatar：角色卡展开后，把现有"头像" URL `FormField` 整块换成 `<ImageField>`（左缩览右入口）；角色卡**收起**时的 36px 小圆继续实时反映 avatar（现有逻辑不动）。

### 状态

| 状态 | 表现 |
|---|---|
| 有图 | 缩览 + 角标入口 |
| 空 / 占位图 | `NO IMAGE` 占位 + 同样可操作 |
| 生成 / 上传中 | 图框半透明遮罩 + 居中转圈，动作禁用 |
| 失败 | **保留旧图** + toast「失败，已保留原图」，可重试 |

### 视觉

沿用 v2.3：动作按钮用 `lv-btn lv-btn-sm` 香槟金描边 + caps 小标签，与编辑器现有按钮（加地点/加角色）同款；不引新样式。移动端触摸目标 ≥ 44px，不依赖 hover 表达状态。

## 后端设计

### 1. 通用上传端点

`POST /api/workshop/uploads`（镜像 `POST /api/auth/me/avatar`）：

- 鉴权：`get_current_user`。
- 入参：JSON `{ image: <data URL>, kind: "cover" | "avatar" }`（`kind` 仅用于决定体积上限）。
- 校验：mime ∈ {png, jpeg, webp}；大小 ≤ 上限（avatar 2MB / cover 5MB）；base64 可解码且非空。
- 落库：`image_storage.save(bytes, make_image_key(...))` → OSS。
- 返回：`{"code":0,"data":{"url":"..."},"message":"ok"}`。
- 与具体字段解耦——前端拿到 url 后写回 draft payload 对应字段。

### 2. 重抽端点（世界）

`POST /api/workshop/world-drafts/{draft_id}/regenerate-image`：

- 鉴权 + **所有权校验**（`draft.user_id == user.id`）。
- 入参：`{ target: "hero" | "cover" | "avatar:<角色名>", hint?: string }`。
- 流程（同步）：
  1. 读当前草稿字段（见下「草稿新鲜度」），用 `derive_world_cover_brief(...)` 重推 `CoverBrief` / `CharacterCoverBrief`（一次廉价文本 LLM 调用，复用世界生成所用文本槽）——重推而非缓存，使其反映用户的最新编辑。
  2. 按 target 选 prompt 构造器：`build_world_hero_prompt` / `build_world_cover_prompt` / `build_character_portrait_prompt`。
  3. 把 `hint` 拼接到 prompt 末尾（有则拼）。
  4. 经 `resolve_slot_image_generator(db, "image_generation")` → `MeteredImageGenerator.generate_image(...)` 生成（计费/重试与初次生成一致）。
  5. 封面 3:2 复用现有服务端裁剪（`image_cropper`）。
  6. `save_generated_image_result(...)` 落 OSS。
- 返回：`{"data":{"url":"..."}}`。

> 注：`derive_world_cover_brief` 一次推全套（世界 + 所有目标角色），单图重抽会算到用不上的部分——v1 接受这点轻微浪费。

### 3. 重抽端点（剧本）

`POST /api/workshop/script-drafts/{draft_id}/regenerate-image`，`{ target: "cover", hint? }` → `build_script_cover_prompt` → 同上 → `{url}`。

### 数据模型

**不新增任何模型**。两条链路都只返回 URL，前端写回 draft payload（`hero_image` / `cover_image` / `character.avatar`），由现有 autosave 持久化、publish 链路搬运。无需 `SessionLock`（非游戏 session，且后端不直接改草稿）。

### 草稿新鲜度

重抽要反映用户刚改的描述。**方案定为：重抽前前端先 flush autosave，后端直接读已持久化的草稿字段推 brief**（后端单一数据源，最简单）。不走"请求体带当前字段"那条，避免前后端两份真相。

## 计费现状（v1）

重抽端点在 `usage_context(purpose="image_gen", user_id=...)` 内调用图像槽（`MeteredImageGenerator`），作为计费挂载点。但 `token_usage` 表的 CHECK 约束要求 `session_id` 或 `task_id` 至少一非空，且二者均为外键（→ `game_sessions` / `generation_tasks`）；独立的单图重抽两者皆无，故该 usage 行被 sink 静默丢弃 —— **v1 重抽实际不计费**。真正计费需为重抽挂一条真实 task 行（或复用草稿已有 task），列为后续。上传不涉及生成，本就无计费。

## 边角与失败处理

- 上传封面比例不符 → `object-fit: cover` 裁切显示 + 一句比例提示，不做手动裁剪。
- 重抽 / 上传失败 → 保留旧图，toast，可重试。
- 生成返回占位图（重试耗尽）→ 当作失败处理，保留旧图。
- 未保存就离开 → 新图已在 OSS 但 URL 未入草稿（孤儿图）：与任何未保存编辑同级别风险，v1 接受。

## 测试

- 后端：上传 mime/size 校验（含超限、非法 data URL）；重抽端点能按各 target 构造 prompt + 落图 + 返回 url；所有权/鉴权拦截。
- 前端：`<ImageField>` 三态（idle / loading / error）；上传读文件→data URL→写回 payload；重抽方向展开。轻量为主。

## 涉及文件（预估）

- 后端：`backend/api/workshop.py`（+3 端点）、复用 `services/image_storage.py` / `services/cover_brief*.py` / `services/metered_image_generator.py` / `services/cover_brief_helper.py`、`schemas/`（请求/响应 schema）。
- 前端：新增 `frontend/components/admin/editor/fields/ImageField.tsx`；改 `CoverDeck.tsx`（挂入口）、世界/剧本草稿页（`app/workshop/{worlds,scripts}/drafts/[id]/page.tsx`）的封面与头像处；`lib/` 加上传/重抽 API 封装；`i18n/zh.json` + `en.json` 文案。
