# 通知 + 系统公告 设计 spec

- 日期：2026-06-05
- 状态：设计已确认，待出实现计划
- 范围：主站（frontend 3000）个人通知 + 系统公告；admin-frontend（3001）公告管理；后端模型/服务/API/触发点

## 1. 背景与目标

InkWild 当前缺一个面向用户的通知能力。已经发生但用户**无感知**的事件包括：注册时已送 500 积分（`credit_service` 的 `signup_grant`）、创作内容被 admin 审核通过/驳回（`admin_review.py` + `publish_service.py`）、内容被强制下架（`withdraw_*(by_admin=True)`）。同时缺少向全体用户广播的「系统公告」（服务器维护、新功能等）。

目标：补齐两类能力，前端走「简洁为主」——一个铃铛 + 弹窗，弹窗内分「通知 / 系统公告」两个 tab（参考 new-api 的轻量形态）。

### 1.1 两类对象的区别

| | 个人通知（notification） | 系统公告（announcement） |
|---|---|---|
| 关系 | 一对一，绑定某个用户 | 一对多，发给全体用户 |
| 产生方 | 系统在事件点自动产生 | admin 手动创建并发布 |
| 例子 | 注册送积分、审核通过/驳回、强制下架、积分不足 | 服务器维护、新功能上线 |
| 已读 | 行上 `read_at` | 读了才在 `announcement_reads` 写一行 |

## 2. 关键决策

1. **架构：双表分离（不扇出）。** 个人通知一人一行；公告一条一行 + 轻量 `announcement_reads` join 表记录已读。放弃「公告发布时给每个用户扇出一行」的方案——避免写放大、避免新用户漏看历史公告。
2. **公告未读判定：** 已发布 且 `published_at >= user.created_at` 且未过期 且当前用户无 read 行。`published_at >= user.created_at` 让新用户不会被注册前的历史维护公告当成未读刷屏；但列表里仍可看到（按已读展示）。
3. **推送：轮询。** 仅 `GET /api/notifications/summary` 一个廉价端点被 TanStack Query 定时轮询（30–60s）拿未读数；列表在打开弹窗时才拉。不引入 SSE 长连接（通知是弱实时场景，简洁优先）。
4. **公告对象：仅全体用户。** v1 不做受众分组；不存 audience 字段。
5. **文案存储：v1 存中文渲染好的 `title`/`body`，同时存 `type` + `payload`（JSONB）** 以便日后做双语模板重渲染，不画死。
6. **公告不做登录强弹横幅**，只进铃铛 tab，靠 `level` 配色 + `expires_at` 自动过期。
7. **个人通知由系统自动产生**，v1 不做 admin 手动给单个用户发（YAGNI）。

## 3. 数据模型（3 张新表，1 个 Alembic 迁移）

### 3.1 `notifications`（个人通知）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK→users | 收件人 |
| `type` | str(32) | `signup_grant` / `review_approved` / `review_rejected` / `content_takedown` / `low_credit` |
| `title` | str(200) | 创建时按中文渲染好 |
| `body` | Text | 同上，可空 |
| `link` | str(500) 可空 | 深链，如 `/workshop/worlds/<id>` |
| `payload` | JSONB 可空 | 结构化数据（draft_id、kind、credit 数等），留作日后模板重渲染 |
| `read_at` | datetime 可空 | NULL = 未读 |
| `created_at` | datetime | |

索引：`(user_id, read_at)`、`(user_id, created_at desc)`。

### 3.2 `announcements`（系统公告）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid PK | |
| `title` | str(200) | |
| `body` | Text | |
| `level` | str(16) | `info` / `warning` / `critical`，仅做前端配色 |
| `status` | str(16) | `draft` / `published`，默认 `draft` |
| `published_at` | datetime 可空 | 发布时置为当前时间 |
| `expires_at` | datetime 可空 | 到点后从列表/未读数中消失 |
| `created_by` | uuid FK→users | 创建的 admin |
| `created_at` / `updated_at` | datetime | |

索引：`(status, published_at desc)`。

### 3.3 `announcement_reads`

| 列 | 类型 |
|---|---|
| `user_id` | uuid FK→users，复合 PK |
| `announcement_id` | uuid FK→announcements，复合 PK |
| `read_at` | datetime |

## 4. 后端服务层（两个小而专的文件）

### 4.1 `services/notification_service.py`

```python
async def notify(
    db, *, user_id: str, type: str, title: str,
    body: str | None = None, link: str | None = None,
    payload: dict | None = None,
) -> Notification: ...

async def list_for_user(db, *, user_id, limit=20, before: datetime | None = None) -> list[Notification]: ...
async def unread_count(db, *, user_id) -> int: ...
async def mark_read(db, *, user_id, notification_id) -> None: ...   # 校验归属
async def mark_all_read(db, *, user_id) -> int: ...

# 带去重的便捷封装：已存在未读 low_credit 就跳过，避免每回合刷屏
async def notify_low_credit_once(db, *, user_id, ...) -> Notification | None: ...
```

- `notify` 不自己 commit，跟随调用方所在事务（与触发事件同事务提交，保证一致性）。
- 归属校验：`mark_read` 必须 `WHERE id=:id AND user_id=:uid`。

### 4.2 `services/announcement_service.py`

```python
async def create(db, *, created_by, title, body, level="info", expires_at=None) -> Announcement: ...   # status=draft
async def update(db, *, announcement_id, **fields) -> Announcement: ...
async def publish(db, *, announcement_id) -> Announcement: ...     # status=published, published_at=now
async def unpublish(db, *, announcement_id) -> Announcement: ...   # 回到 draft（软下架）

# 用户视角
async def list_for_user(db, *, user_id, user_created_at, limit=20, before=None) -> list[tuple[Announcement, bool]]: ...  # (公告, 是否已读)
async def unread_count(db, *, user_id, user_created_at) -> int: ...
async def mark_read(db, *, user_id, announcement_id) -> None: ...  # upsert announcement_reads
async def mark_all_read(db, *, user_id, user_created_at) -> int: ...

# admin 视角
async def list_all(db, *, limit, offset) -> list[Announcement]: ...   # 含草稿
```

未读数 SQL 思路：`count(announcements WHERE status='published' AND (expires_at IS NULL OR expires_at>now) AND published_at>=:user_created_at AND NOT EXISTS(SELECT 1 FROM announcement_reads WHERE announcement_id=announcements.id AND user_id=:uid))`。

## 5. 触发点（埋点，复用现有流程）

| 通知 type | 埋在哪 | 内容要点 |
|---|---|---|
| `signup_grant` | `credit_service` 首次创建钱包发 signup_grant 处 | title「欢迎加入 InkWild」，body 含赠送积分数，payload `{units}` |
| `review_approved` | `api/admin_review.py` approve 成功后 | notify `draft.created_by_user_id`；link 指向已发布内容；payload `{kind, draft_id, target_id}` |
| `review_rejected` | `api/admin_review.py` reject 成功后 | body 带 `review_note`；link 指回草稿编辑；payload `{kind, draft_id, note}` |
| `content_takedown` | `publish_service.withdraw_world/script(by_admin=True)` 分支 | 通知内容作者；payload `{kind, target_id}` |
| `low_credit` | `credit_service` settle/charge 后余额低于阈值 | 用 `notify_low_credit_once` 去重；payload `{balance_units}` |

阈值：余额低于「约一局成本」或一个固定小值（实现时取现有 guardrail 常量或定义 `LOW_CREDIT_THRESHOLD_UNITS`）。

## 6. API 面

### 6.1 用户端 `api/notifications.py`（`get_current_user`）

统一 `{"code":0,"data":...,"message":"ok"}` 包裹。

- `GET /api/notifications/summary` → `{notifications: int, announcements: int}`。**唯一被轮询的端点**，必须廉价（两个 count）。
- `GET /api/notifications?limit=20&before=<iso>` → `{items: [...], next_before: <iso|null>}`。
- `POST /api/notifications/{id}/read` → 标记单条已读（校验归属）。
- `POST /api/notifications/read-all` → 全部已读，返回影响条数。
- `GET /api/announcements?limit=20&before=<iso>` → `{items: [{...announcement, read: bool}], next_before}`。
- `POST /api/announcements/{id}/read`、`POST /api/announcements/read-all`。

### 6.2 Admin 端 `api/admin_announcements.py`（`get_current_admin_user`）

每个写操作调用 `record_admin_action` 审计。

- `GET /api/admin/announcements?limit=&offset=` → 含草稿全量。
- `POST /api/admin/announcements` → 创建草稿。
- `PATCH /api/admin/announcements/{id}` → 编辑。
- `POST /api/admin/announcements/{id}/publish`。
- `POST /api/admin/announcements/{id}/unpublish`。

两个路由都在 `main.py` / app 注册处挂载。

## 7. Schemas

`schemas/notification.py`：`NotificationOut`、`NotificationListOut`、`AnnouncementOut`（含 `read`）、`AnnouncementListOut`、`NotificationSummaryOut`、admin 的 `AnnouncementCreateIn` / `AnnouncementUpdateIn`。

## 8. 前端（主站 3000，简洁为主）

### 8.1 组件

- `components/NotificationBell.tsx`：铃铛图标 + 未读小红点/数字（总未读 = 通知未读 + 公告未读）。挂载点：
  - 桌面：`ProductNav` 右侧（与 LangChip/CreditBalanceChip 同区）。
  - 移动：`MobileTopBar` 的 `right` 槽，与 `CreditBalanceChip` 并排。
  - 未登录不渲染。
- 点击展开：桌面用 Radix **Popover**，移动用 **vaul Drawer**（项目已有），内容为 `components/notifications/NotificationPanel.tsx`：
  - 顶部两个 tab：「通知 / 系统公告」，各自带未读小数字。
  - 列表项：标题 + 相对时间 + 未读点；公告按 `level` 配色左边条；有 `link` 的点击跳转。
  - 底部「全部已读」。
  - 空态：简洁文案。
- 子组件：`NotificationItem.tsx`、`AnnouncementItem.tsx`。

### 8.2 数据层 `lib/notifications.ts`

- 类型 + API 封装（`apiFetch`）。
- TanStack Query hooks：
  - `useNotificationSummary()`：`refetchInterval` 30–60s，`enabled` 仅在已登录时。驱动铃铛角标。
  - `useNotifications()` / `useAnnouncements()`：打开弹窗时才 `enabled`，支持「加载更多」（infinite 或 before 游标）。
  - `useMarkRead` / `useMarkAllRead` mutation：乐观更新角标与列表，成功后 invalidate summary。
- 已读交互（统一）：**点击单项**标记该项已读（同时跳 link，若有）；**不做**打开弹窗即自动已读；底部「全部已读」按钮批量标记当前 tab。

### 8.3 视觉与 i18n

- 走 v2.3 令牌：香槟金 `--lv-accent`、`.lv-t-*` 字号、`var(--lv-*)` 颜色。
- i18n key 进 `i18n/zh.json` + `i18n/en.json`（`notifications.*`）。

## 9. Admin 前端（3001）

公告管理页：列表（标题/level/状态/发布时间）+ 新建/编辑表单（标题、正文、level、过期时间）+ 发布/下架按钮。沿用 admin-frontend 现有视觉系统（不复用主站令牌）。

## 10. 测试（轻量，按项目原则）

后端 pytest：
- `notification_service`：create / unread_count / mark_read 归属校验 / mark_all_read。
- `notify_low_credit_once` 去重：连发两次只剩一条未读。
- `announcement_service`：发布后已读 join；新用户不被 `published_at < created_at` 的旧公告计入未读，但列表可见；过期公告不计未读。
- 审核 approve/reject 各产生一条对应 notification（触发点接通）。

前端 vitest：`lib/notifications.ts` 的解析/未读数合并逻辑一个用例。

## 11. 不做（YAGNI / 明确排除）

- SSE 实时推送、WebSocket。
- 公告受众分组、定向个人通知（admin 手动发给某用户）。
- 邮件 / 站外推送。
- 登录强弹横幅、Toast 化的实时弹出。
- 通知偏好设置（用户关闭某类通知）。

## 12. 涉及文件清单

新增：
- `backend/models/notification.py`
- `backend/schemas/notification.py`
- `backend/services/notification_service.py`
- `backend/services/announcement_service.py`
- `backend/api/notifications.py`
- `backend/api/admin_announcements.py`
- `backend/migrations/versions/<rev>_add_notifications_and_announcements.py`
- `backend/tests/test_notification_service.py`、`test_announcement_service.py`（轻量）
- `frontend/components/NotificationBell.tsx`、`frontend/components/notifications/*`
- `frontend/lib/notifications.ts`
- admin-frontend 公告管理页

改动：
- `backend/services/credit_service.py`（signup_grant + low_credit 触发）
- `backend/api/admin_review.py`（approve/reject 触发）
- `backend/services/publish_service.py`（admin 强制下架触发）
- `backend/main.py`（注册两个新路由）
- `backend/models/__init__.py`（导出新模型）
- `frontend/components/ProductNav.tsx`、`frontend/components/MobileTopBar.tsx`（挂铃铛）
- `frontend/i18n/zh.json`、`frontend/i18n/en.json`
