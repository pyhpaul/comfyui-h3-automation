# ComfyUI 网页可见反馈（不装扩展）设计

**日期：** 2026-09-08  
**状态：** 待用户确认 spec  
**关联：** `2026-09-08-comfyui-h3-remote-orchestration-design.md`  
**决策：** 方案 B — 不装 Comfy 扩展；前端反馈以官方 ComfyUI 网页为准；不追求画布控件回填。

## 1. 背景与目标

编排框架已能：本地 job/inbox → 远端 `/upload` + `/prompt` → 拉回 `outputs/`。  
用户需要在 **ComfyUI 网页**看到任务在跑、跑完有结果，作为「注入并出片」的可见反馈。

经官方文档与源码调研：

- `/prompt` 只入队执行，**不会**改浏览器画布上的 LoadImage/提示词等控件。
- 队列 `status` 会对已连接网页 **广播**；细进度/预览默认发给提交时的 `client_id`。
- 官方路由 **无**「远程改画布 widget」接口；要 A2（控件回填）必须扩展或浏览器自动化。本期不做。

**本期成功标准：**

1. 用 mock 资产包（或真实 job 目录）完整走通：产资产 → `watch`/`submit` → 远端执行 → 本地 `outputs/<job-id>/`。
2. 执行期间浏览器打开同一 Comfy 实例，能看到 **队列变化**；跑完能在 Comfy 输出预览或历史中看到结果（视前端版本而定）。
3. 文档写清：能看见什么 / 看不见什么；可选如何传 `client_id` 改善细进度。
4. **不**要求画布节点控件随 API 注入实时改写。

## 2. 范围

### 做

| 项 | 说明 |
|----|------|
| Demo 路径固化 | 保留/完善 `scripts/mock_produce_assets.py` → `inbox/` → `comfy-orch watch` |
| 可选 `client_id` | CLI 与/或环境变量传入；写入 `POST /prompt` 的 `client_id`，便于对齐浏览器 WebSocket |
| README 操作说明 | 先开 Comfy 页再跑 watch；队列可见；可选 DevTools 抄 `clientId` |
| 回归 | 现有单测保持绿；对 vm122（或当前 `COMFY_BASE_URL`）再跑一轮 mock 冒烟 |

### 不做

- Comfy 自定义节点 / 前端扩展 / `loadGraphData` 同步画布
- 浏览器自动化操作 Comfy 页面
- 自建第二套「监控大屏」前端（用户明确要看 Comfy 官方页）
- YZ 金鱼 / H3 租卡模板接入（可后续独立任务；本期 demo 继续用 `smoke_passthrough`）
- 多卡并行、改一期串行策略

## 3. 用户可见行为（Comfy 网页）

| 现象 | 期望 |
|------|------|
| 队列剩余数 / 侧栏任务 | 应能看到 API 提交的任务（`status` 广播；现代前端还会轮询 `/queue`） |
| 节点逐步高亮、潜空间预览 | **可选增强**：仅当提交使用的 `client_id` 与浏览器 WS 的 `clientId` 一致时更可靠 |
| LoadImage 缩略图、文本框被改掉 | **不保证、不实现** |
| 成片 | Comfy 输出区 / History；本地 `outputs/<job-id>/` 与 `runs/<job-id>/status.json` |

## 4. 架构与数据流

```text
[mock_produce_assets / 上游资产包]
        → inbox/<job>/job.yaml + assets/
        → comfy-orch watch|submit
        → upload + bind + POST /prompt (± client_id)
        → Comfy 执行（浏览器已打开同一 BASE_URL）
        → 本地 history 轮询 + /view → outputs/
```

- 仍只认 `COMFY_BASE_URL`。
- `client_id`：**可选**。未设置时行为与现网一致（队列仍应可见；细进度可能只在提交方 WS）。
- 获取浏览器 `clientId` 的方式（文档说明即可）：浏览器 DevTools → Network → `ws` → 查询参数 `clientId`；复制到：
  - `export COMFY_CLIENT_ID=...`，或
  - `comfy-orch submit|watch --client-id ...`
- 不实现「自动探测浏览器 client_id」（需扩展或自动化，超出 B）。

## 5. 实现要点

### 5.1 Client / Runner / CLI

- `ComfyClient.queue_prompt`（或等价）支持可选 `client_id`，放入 JSON 根级（与官方 `websockets_api_example.py` 一致）。
- `submit_job` / `process_inbox_once` / `watch` 透传该参数。
- CLI：`submit`、`watch` 增加 `--client-id`；若未传则读 `COMFY_CLIENT_ID`；都空则省略字段。

### 5.2 Demo 脚本

- `scripts/mock_produce_assets.py`：生成 N 个 `smoke_passthrough` job 到 `inbox/`（已有则保持行为，按需小改文档对齐）。
- README 增加「可见反馈 Demo」小节：开网页 → produce → watch → 看队列与 `outputs/`。

### 5.3 错误与状态

- 域名错误仍写 `runs/*/status.json` failed；inbox 进 `.failed/`。
- `client_id` 错误/过期不单独校验（Comfy 无强校验）；文档注明抄错则细进度仍可能对不齐，但不影响出片与拉回。

## 6. 测试

- 单测：`queue_prompt` 在传入 `client_id` 时 body 含该字段；未传时不含或为省略。
- 手工：vm122 上 mock 2～3 job + 浏览器开着 8188，确认队列有任务且本地 outputs 有文件。

## 7. 风险与后续

| 风险 | 缓解 |
|------|------|
| 不同前端版本队列 UI 差异 | 文档以「队列/History/本地 outputs」三重验收 |
| 用户期望画布回填 | Spec 明确不做；若要 A2 另开「同步扩展」专题 |
| H3 真出片 | 另任务：YZ API 模板 + bindings + 租卡 |

后续可选：`client_id` 对齐的体验优化、YZ 模板、或单独的画布同步扩展（非本期）。
