# Park-IO Outbox 本地工作台 v1 PRD

## 目标

把 `/Users/wendy/park-io/outbox/dashboard.html` 从静态进度页升级成本地内容工作台。第一版只解决一件事：让 Wendy 每天能看清楚每条成熟抖音视频已经生成了哪些平台资产、哪些草稿需要校对、哪些可以迁移发布、哪些已经进入 `sent`。

## 产品边界

- 工作台继续由 `/Users/wendy/work/content-ops/scripts/build_dashboard.py` 生成。
- 工作台默认仍可作为本地静态 HTML 查看；需要平台动作时，通过本地 action server 打开。
- 本地 action server：`python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788`。
- 动作页入口：`http://127.0.0.1:8788/dashboard.html`。
- `file://` 查看模式只能打开本地草稿/素材包、展示下一步命令、跳转到已有文件。
- `http://127.0.0.1:8788` 模式允许点击按钮调用本地工具推送平台草稿。
- 真正发布仍然需要 Wendy 人工确认。
- 数据边界不变：`content-ops` 负责编排，`outbox` 负责存放 drafts/sent 和 dashboard。

## 页面结构

1. 顶部进度区：展示各平台 sent/drafts/target/gap。
2. 内容矩阵：行是抖音源视频，列是小红书、公众号、视频号、Bilibili、YouTube、知乎、X。
3. 详情区：点击任一抖音源视频后，展示源内容路径、转录状态、organized transcript、各平台草稿和下一步动作。
4. 审核队列：突出小红书、公众号、知乎、X 这些需要人工编辑的平台。
5. 迁移队列：突出 Bilibili、视频号、YouTube 这些可直接搬运的平台。
6. 动作区：支持检查通道、打开平台后台、推送到草稿箱。
7. 登录检查：每个平台显示 `检查登录`，返回本地 cookie/API/tool readiness。
8. 通道准备：每个平台显示 `准备通道`，用于启动 bridge、打开登录页、安装 runtime 或打开后台。
9. 批量准备：顶部显示 `准备缺失通道`，只对当前不可用且可准备的平台发起登录/bridge/runtime 准备动作，不发布内容。
10. 最近动作：显示最近的检查、准备、推送、交接、标记发送动作，避免动作结果只存在弹窗 JSON 里。
11. 单条预检：详情区显示 `预检这条内容`，一次检查该源内容在所有平台的本地草稿、视频文件、图文包、登录态和交接可用性。
12. 本地素材修复：当小红书预检缺图文包时，提供 `生成小红书图文包`，只运行本地质量检查和渲染，不触碰平台后台。
13. 单条原视频修复：当视频号/Bilibili/YouTube 预检显示视频源缺原视频时，提供 `修复这条原视频`，只修当前 source id。
14. 单条本地草稿生成：当预检显示某平台缺 `local_draft` 时，提供 `生成本地草稿`，只为当前 source id 和平台写入 `outbox/drafts/<platform>`。
15. 单条本地缺口批量修复：预检存在本地草稿/小红书图文包缺口时，提供 `补齐本地缺口`，一次性生成缺失平台草稿并渲染小红书图文包。

## 动作服务规则

- 所有平台动作都必须经过浏览器确认框。
- API 层也要求 `confirmed=true`，避免误触。
- `push-draft` 只允许“填表/保存草稿”，不实现最终发布。
- 小红书当前可用：读取已渲染图文包，调用 `xiaohongshu-skills fill-publish`，再调用 `save-draft`。
- 公众号当前可用：读取 `outbox/drafts/wechat_mp/*.json|*.md`，调用 `wechat-workflow` bridge 创建公众号草稿。
- 视频号当前可用：读取原视频文件和视频号本地草稿，调用 `TencentVideo(is_draft=True)` 保存草稿；需要有效 cookie。
- Bilibili 当前走安全 self-only upload：账号 cookie 就绪后调用 `biliup --is-only-self 1` 上传为仅自己可见；不公开发布，仍需在 Bilibili 创作中心手动检查后发布。
- 知乎 / X 当前接入安全 handoff：打开平台后台/编辑页，把标题、正文、视频路径放入剪贴板；不调用发布命令。
- YouTube 当前走安全 private upload：OAuth 就绪后调用 YouTube API 上传为 private 视频；不公开发布，仍需在 YouTube Studio 手动检查后发布。
- `prepare-missing-channels` 可以一次性拉起缺失通道的准备动作，但不会绕过登录、验证码、扫码或 OAuth 授权。
- `actions/recent` 只读取本地 action log 的摘要，不暴露完整正文或 secret。
- `preflight-source` 只读本地文件和通道状态，不创建平台草稿，不打开后台，不写剪贴板。
- `prepare-local-asset` 第一版只支持小红书：运行 `quality_xiaohongshu_drafts.py --force` 和 `render_xiaohongshu_cards.py --style dense`。
- `repair-missing-videos` 在详情预检里传入 `source_content_ids: [id]` 时只修当前源内容，不跑全库。
- `generate-local-draft` 调用 `generate_repurpose_drafts.py --source-content-id <id> --platform <platform>`，只生成本地草稿，不触碰平台。
- `repair-local-gaps` 只处理本地草稿和小红书图文包，不下载视频，不打开平台后台，不发布。

## 状态定义

- `missing`：该平台还没有对应草稿或 sent 记录。
- `draft`：已有草稿，但仍处在普通草稿状态。
- `review_needed`：已有草稿，需要人工编辑或质量检查。
- `ready_to_package`：小红书已通过质量层，但还没有图文包。
- `packaged`：小红书图文包已渲染，或平台素材包已准备好。
- `sent`：已进入 `outbox/sent/<platform>/`。

## 平台规则

- 抖音：source of truth，成熟视频在 `outbox/sent/douyin`。
- 小红书：必须走 `polish -> quality -> render -> review`，工作台显示 `xhs_quality` 和图文包入口；渲染完成后可以从 dashboard 推送到小红书草稿箱。
- 公众号：可推送到公众号草稿箱，但仍需要人工在公众号后台编辑审核。
- 知乎 / X：文本平台草稿，默认需要人工编辑审核。
- 视频号：可保存平台草稿，重点检查标题、简介、视频、封面。
- Bilibili：走仅自己可见上传，重点检查标题、简介、视频、封面；不会公开发布。
- YouTube：走 private upload，重点检查标题、简介、视频、封面；不会公开发布。
- 知乎 / X：先走 handoff，打开编辑入口并准备文本；不直接发布。
- 发布后统一记录到 `outbox/sent/<platform>/`，`drafts` 只代表未发送内容。

## 验收标准

- `python3 /Users/wendy/work/content-ops/scripts/build_dashboard.py` 能生成 `dashboard.html`、`assets.json`、`platform-summary.json`。
- 页面显示 14 条抖音源内容。
- 矩阵列包含小红书、公众号、视频号、Bilibili、YouTube、知乎、X。
- 小红书 722394 的 8 条草稿显示质量状态和草稿入口。
- Bilibili / 视频号 / YouTube 显示可迁移草稿入口。
- 页面不把 `_cache`、debug、reports 当成人类工作区入口。
- 本地浏览器打开后，平台筛选可用，点击源内容能更新详情区。
