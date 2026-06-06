---
target: 前端移动端 (app-first)
total_score: 32
p0_count: 0
p1_count: 0
timestamp: 2026-06-05T09-00-43Z
slug: frontend-mobile-app-first
---
# InkWild 前端移动端（app-first）设计评测

## Design Health Score（移动端视角）

| # | 启发式 | 分 | 关键问题 |
|---|--------|----|---------|
| 1 | 系统状态可见性 | 3 | play 有里程碑 loading / streaming / processingHint，强；其余页 OK |
| 2 | 贴合现实世界 | 4 | 中文自然语言 + 故事隐喻，对玩家零术语 |
| 3 | 用户控制与自由 | 3 | 退场意图确认、PauseOverlay、retry、exitHref 回流齐全 |
| 4 | 一致性与标准 | 4 | lv-* 令牌 + 9 档字号 + 统一导航，全站高度一致 |
| 5 | 错误预防 | 3 | 退场二次确认（聪明）、streaming disabled、ConfirmDialog |
| 6 | 识别优于回忆 | 3 | BottomTabBar 带文字标签（非纯图标），导航始终可见 |
| 7 | 灵活与效率 | 3 | QuickActions、drawer 偏好持久化、Enter 发送、拇指区 |
| 8 | 美学与极简 | 4 | 电影感、克制金、无假指标、无堆砌 |
| 9 | 错误恢复 | 3 | openingFailed 重试、错误 toast、CenterMessage 兜底 |
| 10 | 帮助与文档 | 2 | 几乎无 onboarding / 空状态教学 |
| **总分** | | **31/40** | **Good（弱项=帮助/首run，单点 login 溢出）** |

## Anti-Patterns Verdict
detector 扫 app+components 共 13 处：4 处在 /dev sandbox（忽略），其余多为误报/admin 性能 nit。无结构性 AI-slop（无渐变文字、无侧边条、无玻璃拟态滥用、无 hero-metric 模板、无米色默认底）。整体不像 AI 生成，符合 brand spec。

## What's Working
1. 移动优先已制度化：AGENTS.md 有「移动端检查项」PR 清单，globals.css 零 100vh、dvh×9、safe-area×8，BottomTabBar/MobileTopBar/play-composer 全处理刘海安全区。
2. play 沉浸态扎实：单栏 play-stage + 底部 composer（安全区 + 渐隐遮罩）+ 完整 loading/error/retry/pause 状态机；沉浸态自动隐藏 tab bar。
3. 视觉系统成熟：landing/discover 在窄屏完美 reflow，香槟金 + 暖象牙 + 衬线大标题，双 CTA 同时对玩家与创作者说话。

## Priority Issues
- **[已撤回，非 bug] /login 移动端横向溢出**：初判 P1，经 CDP `Emulation.setDeviceMetricsOverride` 真机视口复测证伪——375/390px 下 `docScrollWidth == innerWidth`、`offendersCount == 0`，`.auth-card` 宽 300px 居中（left 38–45）完全 fit。误判根因=headless 把 innerWidth 强制成 500px，420px 居中卡被 390px 截图画布裁掉右侧 ~70px。代码无需改动。
- **[P2] play 案件板/侧边抽屉被 flag 关闭**：`PLAY_SIDE_PANEL_ENABLED = false`，文档化的核心功能（案件板）当前在 play 页隐藏，「完成度」缺口。这是评测里唯一真的「未完成」项。
- **[P3] play 发送按钮 42px < 44px**：`.play-compose-submit` 略低于触摸目标下限。
- **[P3] landing 用 Inter（detector overused-font）**：可接受（body 用，品牌声音由衬线承载），但可考虑换更有个性的 UI sans。

## Persona Red Flags
- **Casey（单手移动用户）**：主动线（landing→discover→world→play）拇指区与状态保持良好；/login 经复测在 375/390px 正常居中无裁切。
- **Jordan（首次用户）**：无 onboarding / 空状态教学，首次进 play 靠旁白自解释；help 维度弱。

## Minor Observations
- BottomTabBar 标签 9px mono，极小但可读（刻意）。
- landing hero 金色标题压在雾色图上，局部对比度需抽查 ≥4.5:1。
- admin/account 若干 layout-transition（height/width 动画）性能 nit，非玩家移动面，低优先。
