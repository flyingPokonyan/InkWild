# 创作发布生命周期设计（私有库 + 审核公开）

- 日期：2026-05-30
- 状态：设计已确认，待落实施计划
- 关联：创作工坊（`docs/modules/world-creator.md`）、积分系统（`backend/services/credit_service.py`）、内容状态机（`backend/engine/content_status.py`）

## 1. 背景与问题

创作工坊当前流程：AI 生成 → 存为 `world_drafts`/`script_drafts`（JSON payload，**不可玩**）→ 点「发布」→ 落成 `World`/`Script` 行且 `status="published"` → **立即全网可见**（discover feed）。

两个问题：

1. **创建即全网不合理。** 用户的「发布」端点写死 `audit_enabled=False → published`，没有任何中间态，也没有审核闸门。
2. **没有"自己玩"的能力。** 发布前作品只是草稿 JSON，无法游玩；玩游戏读的是 `World`/`Script` 行。所以创作者要么不发布（玩不了），要么一发布就全网。

核心缺口：缺少一个**真实可玩、但不公开**的状态。今天是二元的——不可玩草稿 ↔ 全网世界。

## 2. 目标 / 非目标

**目标**
- 引入「私有可玩」一等公民持久态：创作者可长期保留只有自己能玩的世界/剧本（个人 AI 游乐场）。
- 「发布到全网」拆成独立、刻意的动作，且需经 admin 审核。
- 已发布作品可正常编辑并重新提交审核，**线上版本不下线**。

**非目标**
- 不做"链接分享/指定好友可见"等更细可见性（YAGNI）。
- 不做自动化内容审核流水线（沿用现有 `content_filter`/`moderation` + 人工审核队列）。
- 不改积分计费模型（私玩照常按局扣费，与公开玩一致）。

## 3. 已确认决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 私有定位 | **永久私有库**（一等公民持久态） | 创作者可长期私有保留，发布只是可选动作 |
| 私玩计费 | **照常扣分**（≈25/局，与公开一致） | 简单一致；杜绝"全设私有=无限免费玩"漏洞（LLM token 谁玩谁产生） |
| 公开闸门 | **私有 → 提交审核 → admin 通过 → 全网** | 上线前保证公开 feed 质量 |
| 落地方案 | **方案 B**：显式「保存为私有」+ 独立「提交发布」 | 复用现有 draft→publish 管线，改动最小；草稿态=迭代工作台仍有意义 |
| 审核粒度 | **世界 / 剧本各自独立审核** | 现基本一世界一剧本；解耦更灵活 |
| 改版策略 | 已发布可**直接编辑 + 重新提交**，线上不下线 | 不强制"先下架才能改"的摩擦 |

## 4. 状态模型

### 4.1 作品可见性 —— `World.status` / `Script.status`（三态）

- `private` —— 私有可玩，仅 owner 可见可玩（**新建默认**）
- `published` —— 全网可见
- `withdrawn` —— 被 admin 强制下架（owner 不能自助恢复）

> 移除 World/Script 行上对 `submitted` 的语义使用（见 4.2）。`Script.is_published` 保留为 `status == "published"` 的镜像布尔（兼容现有消费方）。

### 4.2 审核态 —— 挂在草稿上（`world_drafts` / `script_drafts` 新增字段）

- `review_status`: `editing`（默认/有未提交改动）｜ `submitted`（审核中）｜ `rejected`（被驳回）
- `review_note`: `str | None` —— 驳回理由

**为什么挂草稿而不挂 World：** 已发布作品改版时，线上行必须保持 `published`，同时存在一个"审核中"的修订版。World 不可能既 `published` 又 `submitted`。把审核态挂在草稿（编辑缓冲）上，首发（private + 草稿 submitted）和改版（published + 草稿 submitted）用**同一套机制**，World 永不进入 `submitted`。

「审核中」徽章 = 该作品存在 `review_status == submitted` 的草稿。

### 4.3 状态转换

```
草稿(JSON, review=editing)
   │ 保存为私有
   ▼
私有 World(private)  ──提交发布──▶  草稿 review=submitted（World 仍 private）
   ▲                                      │ admin 通过            │ admin 驳回
   │ owner 下架                            ▼                      ▼
   │                              World→published          草稿 review=rejected
已发布 World(published) ◀──────────────┘                    (+review_note, World 不变)
   │ 编辑(草稿 review=editing) → 提交(submitted) → 通过 → 应用草稿到 World(仍 published)
   │ admin 下架
   ▼
withdrawn(admin 强制；owner 不可自助恢复)
```

World 行级合法转换：`private→published`、`published→private`（owner 下架）、`published→withdrawn`（admin）。**`withdrawn` 为终态**——owner 不能自助恢复（admin 恢复暂不在范围内；实施时去掉了 `withdrawn→private` 以杜绝 owner 借 withdraw 动作把被下架内容拉回私有）。

## 5. 创作者操作（工坊）

| 当前态 | 可见动作 | 结果 |
|---|---|---|
| 草稿（生成中/调整中，无 World 行） | 重新生成 · **保存为私有作品** · 删除 | 保存 → 建 `World(private)`；保存时跑 **schema 校验**保证可玩不崩 |
| 私有 | **试玩** · 编辑 · **提交发布** · 删除 | 提交 → 草稿 `submitted`（校验见 §6） |
| 审核中（submitted） | 试玩 · 编辑（改了重新提交即可）· **撤回提交** | 撤回 → 草稿回 `editing` |
| 被驳回（rejected） | 看驳回理由 · 编辑 · 重新提交 | 重新提交 → `submitted` |
| 已发布 | 试玩 · 查看公开页 · **编辑（改完重新提交，线上不下线）** · **下架转私有** | admin 通过 → 新版应用到线上行（仍 published） |

世界、剧本各自独立走这套生命周期。

## 6. 校验规则

- **保存为私有**：跑现有 schema 校验（`validate_world_payload` / `validate_script_payload`），保证内容能被引擎正常加载、不崩。私有可玩的前提。
- **提交发布（世界）**：**无额外依赖校验**（世界可在自由模式独立游玩）。
- **提交发布（剧本）**：校验其依附世界**已 `published`**（存在可公开游玩的世界）；否则**禁止提交**，提示「请先发布世界」。在提交时与 admin 通过时各校验一次（防止提交后世界又被下架）。
- 现有 `cross_artifact_validator`（事件↔角色、结局↔线索）在剧本提交/通过时继续跑。

## 7. 访问控制（关键，含隐私）

### 7.1 游玩闸门 —— `game_service.start_game`

当前：只校验 World 行存在；剧本模式校验 `is_published`。**补成：**

- World：`status == "published"` **或** `world.created_by_user_id == current_user.id`，否则 `40001`/`403`。
  （顺手堵上现在"任意 world_id 都能开局、含 withdrawn"的隐患。）
- 剧本模式：`script.is_published` **或** `script.created_by_user_id == current_user.id`（且 `script.world_id == world.id`），否则 `40008`。

### 7.2 `api/worlds.get_world`

当前无鉴权依赖、非 published 一律 404。改为：加 **optional auth**；世界非 published 时，仅 owner 可取（给 play 页 / 工坊预览用），非 owner 仍 404。`list_worlds`（discover feed）**不变**，只出 published。

### 7.3 owner 隔离（隐私）—— `api/workshop.list_workshop_worlds`

当前「已发布」列表**全局可见**（无 owner 过滤），仅草稿按 owner 隔离。新增的 `private`/`submitted`/`rejected` 作品**必须严格按 `created_by_user_id == user` 隔离**（admin 可见全部）。响应每项加 **`is_owner`** 标记，前端据此决定是否渲染 owner 专属动作（下架/编辑/提交）。已发布世界仍对所有创作者可见（保持现有行为）。

`scripts` 列表（`list_workshop_scripts`）做同样的 owner 隔离与 `is_owner` 标记处理。

## 8. 后端改动清单

- **models**：`world_drafts`/`script_drafts` 加 `review_status`（默认 `editing`）、`review_note`（nullable）。`World.status`/`Script.status` 列默认值改为 `private`。
- **migration（Alembic）**：加两列；现有 `published` 世界、seeds（无垠镇）保持 `published`（目前无 private 世界，无数据迁移风险）；保险起见把任何残留 `draft` 状态的 World/Script 行映射为 `private`。
- **`engine/content_status.py`**：状态集与转换表改为 §4.3；`next_status_on_withdraw(by_admin=False)` 返回 `PRIVATE`（原 `DRAFT`）。审核态不再由 World status 表达。
- **`services/publish_service.py`**：拆分/重命名为
  - `save_as_private(draft_id, actor)` —— 草稿 → `World(private)`/`Script(private)`，跑 schema 校验（即原 `publish_*_draft` 的 apply 部分，目标态改 private）。
  - `submit_for_review(kind, id, actor)` —— 置草稿 `review_status=submitted`；剧本跑世界依赖校验。
  - `withdraw_submission(kind, id, actor)` —— `submitted → editing`。
  - `approve(kind, draft_id, admin)` —— 应用草稿 → World/Script 置 `published`；草稿 `review_status=editing`；跑校验 + cross-artifact。
  - `reject(kind, draft_id, admin, note)` —— 草稿 `review_status=rejected` + `review_note`。
  - `withdraw_world/script` —— owner → `private`，admin → `withdrawn`（语义沿用，目标态调整）。
- **`api/workshop.py`**：
  - `POST /world-drafts/{id}/publish` → 语义改为「保存为私有」（调 `save_as_private`）；同理 script。
  - 新增 `POST /world-drafts/{id}/submit`、`/script-drafts/{id}/submit`、`.../withdraw-submission`。
  - `list_workshop_worlds` / `list_workshop_scripts`：纳入 owner 的 private/submitted/rejected，加 `is_owner`、`review_status`、`review_note`。
  - `withdraw` 端点目标态调整为 private（owner）。
- **`api/worlds.py`**：`get_world` 加 optional auth + owner 放行。
- **`services/game_service.py`**：`start_game` 加 §7.1 访问闸。
- **`api/admin.py`（或新 `api/admin_review.py`）**：新增审核队列端点（§9）。

## 9. Admin 审核队列

- **API**（走现有 `get_current_admin_user` + `record_admin_action`）：
  - `GET /admin/reviews` —— 列出 `review_status == submitted` 的世界/剧本草稿（带预览摘要、提交人、提交时间）。
  - `GET /admin/reviews/{kind}/{draft_id}` —— 预览完整 payload。
  - `POST /admin/reviews/{kind}/{draft_id}/approve` —— 调 `publish_service.approve`。
  - `POST /admin/reviews/{kind}/{draft_id}/reject` —— body 带 `note`，调 `publish_service.reject`。
- **admin-frontend（端口 3001）**：新增审核队列页：列表 → 预览 → 通过/驳回(填理由)。沿用 admin 设计基线，不复用主站视觉系统。

## 10. 前端改动（主站工坊）

- 工坊卡片按 §5 状态渲染动作 + 徽章（私有/审核中/已发布/被驳回 + 驳回理由）；owner 专属动作受 `is_owner` 门控。
- 私有作品「试玩」入口 → `worlds/[id]` / `play`；play 相关页对 owner 放行私有内容。
- 「保存为私有作品」「提交发布」「撤回提交」「下架转私有」按钮与确认弹窗。
- 状态/动作走 TanStack Query；i18n `zh.json`/`en.json` 新增文案。
- 遵循 v2.3 视觉令牌与 `frontend/AGENTS.md` 约定。

## 11. 积分交互

无新增计费逻辑。私玩走 `game_service.start_game` → `credit_service.reserve/settle`，与公开玩**完全一致**（≈25/局起）。生成仍各自扣费（世界≈70/剧本≈200）。

## 12. 实施分期

- **P1（私有可玩落地，先消灭"创建即全网"）**：三态 + `save_as_private`（重定向现「发布」端点）+ §7 访问闸 + owner 隔离 + 工坊卡片私有态。**此期结束：创作者能私有游玩，任何东西都不会自动全网。**
- **P2（公开闸门）**：草稿审核态 + `submit_for_review`/`approve`/`reject` + admin 审核队列 + 驳回理由 UI。

## 13. 风险与未决

- **隐私回归风险**：owner 隔离一旦遗漏，私有内容可能泄露给他人。`get_world`、`start_game`、工坊列表三处必须各自显式校验 owner —— 列入测试重点。
- **草稿"脏"指示**：approve 后草稿仍在（编辑缓冲），需用"内容是否与线上一致"驱动「有未提交修改」徽章，而非"草稿是否存在"。实现细节留给计划。
- **历史 `withdraw→published` 直转**：原状态机允许 `withdrawn→published`；新模型改为 `withdrawn→private`（再走提交）。需确认无消费方依赖旧直转。

## 14. 测试（轻量，按项目惯例）

- 单测：状态机转换表；`publish_service` 各动作（save_as_private/submit/approve/reject/withdraw）；剧本提交的世界依赖校验。
- 关键路径：owner 能私玩自己的 private 世界/剧本；非 owner 被 404/403 挡住（隐私）；提交→通过→全网可见；已发布改版不下线。
- 不为边角态补大量测试。

## 15. 实施记录（2026-05-30，P1 + P2 已落地并验证）

后端 60 个相关测试通过；frontend / admin-frontend 生产构建通过；Alembic 单 head。

落地与设计的差异 / 补充：
- **`withdrawn` 改为终态**（见 §4.3）。
- **`save_*_as_private` 对已发布行加保护**：编辑一个已 published 的世界/剧本并点「保存为私有」时，**不降级、不应用到线上**——改动只留在草稿，直到重新「提交发布」经审核后才替换线上。避免静默下架 + 绕过审核两个坑。
- **编辑器 CTA**：草稿编辑器只保留「保存为私有作品」（repoint `endpoints.publish` → `/save-private`），公开动作全部收敛到工坊卡片。
- **admin 审核队列**落在既有 `/content`「内容审核」页（原占位页）。
- **移动端工坊**：本期只做到状态徽章正确 + owner 点按进编辑/访客进试玩；私有→提交发布等生命周期按钮在移动端为后续快跟（发布流程桌面优先）。
- **测试基建坑**：`dependencies.get_db` 与 `database.get_db` 是两个不同函数对象，conftest 只覆盖了前者；admin 路由若 `from database import get_db` 会在测试里命中真 Postgres。新 admin 路由统一 `from dependencies import get_db`。
- **部署提醒**：上线需 `alembic upgrade head`（新增 `world_drafts/script_drafts` 的 `review_status`/`review_note` 两列）；本机构建用 `next build --webpack`（Turbopack native binding 缺失）。
