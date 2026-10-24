# 项目音画审核 MCP 接入

状态：**项目 MCP 已配置、启用；无独立 key 的 Grok CLI 密帧筛查已实测；原生联合音画未验证。**
没有原生 API key 时可走下述「无独立 key 的视觉筛查」，不宣称联合音画审核通过。
此前方案见 `2026-10-23-unit-av-review-implementation-design.md`。

## 执行清单

- [x] 配置与路径边界、原生请求/响应、失败状态的测试先行。
- [x] 本地 stdio MCP：status / inspect_clip / review_clip。
- [x] Gemini 原生视频 inline 请求代码，显式采样率，不借用 Cursor 登录令牌。
- [x] 项目 `.cursor/mcp.json`，非秘密 profile，隔离 SDK 依赖。
- [x] 单测、静态校验、MCP 握手与 Cursor CLI 真实调用。
- [x] 更新 skill 入口及用户操作说明，记录仍缺的 key/效果验证。
- [ ] 配置真实 key 后做原声/静音原生 API 对照，再做坏例校准。

约束：首版只允许 `runs/visual_qc/` 下 MP4，最大 12 MiB / 30 秒；每次一个请求，无自动重试。
上传必须显式 `allow_upload=true`，并提供预先 inspect 得到的源 SHA256。
模型结果只作建议，不自动登记 STRICT、改 NAS 或重渲。

## 文件与职责

- `.cursor/mcp.json`：项目级 stdio 服务 `h3-av-review`，只批准此服务，没有全局放开 MCP。
- `scripts/ops/unit_av_review_mcp.py`：SDK 2.3.0；PEP 723 + 同名 `.lock`，由 uv 隔离启动。
- `config/av_review_profiles.toml`：非秘密 provider/base_url/api_key_env/model；默认 Gemini 3.8 Flash。
- `src/comfy_orch/av_review/`：profile 校验、媒体边界、请求/响应、证据归档分离。

只支持官方 Google 原生 endpoint，不把 Gemini profile 当 OpenAI-compatible chat 请求。
不读取 Cursor/Codex 登录存储；不在项目 `.env`、MCP JSON、profile 或日志里放真实 key。
`uv --no-env-file` 也避免自动加载项目 `.env`。

## 现在如何操作（当前 WSL）

从项目根目录启动 CLI。这版 CLI 实测不会展开 `${workspaceFolder}`，所以配置使用相对路径；
profile 相对路径由服务按项目根解析，不依赖用户 Windows 路径。

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
cursor-cli mcp list-tools h3-av-review
```

应列出 `av_review_status`、`av_inspect_clip`、`av_prepare_visual_clip`、`av_review_clip`。
本机已经执行 `cursor-cli mcp enable h3-av-review`；新机器/配置变更后可能需要再次批准此服务。
uv 与 ffprobe 必须在该操作系统的 PATH 中；首次启动要下载锁定 SDK，之后使用缓存。

### 原生 Gemini 调用所需凭据（当前暂缓）

在本地终端隐藏输入，不把 key 贴到聊天或写入项目文件：

```bash
read -rsp 'Gemini API key: ' GEMINI_API_KEY
export GEMINI_API_KEY
printf '\n'
```

然后从**同一终端新启动** Cursor CLI，让新 MCP 进程继承环境：

```bash
cursor-cli --model grok-4.7-medium '只调用 h3-av-review 的 av_review_status，报告配置状态，不上传素材。'
```

有 key 时应为 `CONFIGURED_NOT_LIVE_VERIFIED`，这仍不表示 key 有效、账号有额度或模型效果通过。
当前实测状态是 `API_KEY_MISSING`。若需长期保存，请使用本机 secret manager，再注入启动环境；
不要将 WSL 的配置依赖到 Windows 登录令牌或绝对密钥路径。

### 正式短片测试提示词

```text
使用 h3-av-review MCP 对我授权的这条短片做一次音画能力测试：
runs/visual_qc/browser-av-probe-20261023/inputs/sample-k7.mp4
先调用 av_review_status，再 av_inspect_clip。
只有 profile/key 就绪、且本地检查通过时，使用检查返回的精确 SHA256，
调用 av_review_clip，allow_upload=true，fps=8，仅一次请求。
失败或超时不要自动重试；报告证据目录、实际返回、限制和不可验项。
不能把模型建议当成人工 V2 或 fix_registry 通过。
```

这段提示明确授权向配置的 Google 原生接口发送指定短片，可能产生 API 费用。
控制 agent 可用 Grok/GPT/Gemini；后台审片模型由 profile 决定，两者不必相同。
`fps=8` 仅是请求参数；服务始终保留 `effective_fps=UNVERIFIED`，实测前不声称 8 FPS 已生效。

## 工具与产物

| 工具 | 是否发送素材 | 用途 |
|---|---|---|
| `av_review_status()` | 否 | profile、key 是否存在、ffprobe 可用性；不验证在线能力 |
| `av_inspect_clip(media_path)` | 否 | 受限路径、大小/时长、视频参数与 SHA256 |
| `av_prepare_visual_clip(media_path, expected_sha256, fps=4)` | 否 | 本地生成带时间戳 JPEG 和清单，无需模型 key |
| `av_review_clip(media_path, expected_sha256, allow_upload=false, fps=8)` | 只有显式授权才发送 | 一个原生视频请求、结构化建议与本地归档 |

发送前再次核对源文件 hash，禁止路径/符号链接逃出 `runs/visual_qc/`；不接受任意上传 URL。
限定官方 HTTPS endpoint，禁用重定向，API key 仅走 header，无自动重试。
缺 key 会在网络请求前退出；超时/请求失败写 `REQUEST_FAILED_OUTCOME_UNKNOWN`，不猜计费或成功。

每次网络尝试输出新目录 `runs/visual_qc/av_mcp/<time-id>/`：
`request-manifest.json`、`review-prompt.txt`、成功时 `provider-response.json`、`report.json`。
不保存请求里的视频 base64，不覆盖原片或旧人审记录；原始响应仅本地留存。
`MODEL_RESPONSE_RECORDED` 只是结构化响应被保存，不是能力通过；无效时码/截断输出会标 INVALID。
本阶段是盲测内容探针，尚未实现剧本全集对齐、人物参考包、自动校准与完整 L2 工单集成。

## 无独立 key 的视觉筛查（当前优先）

```text
本地 MCP：inspect/hash → prepare_visual_clip
    → Cursor CLI 已有 Grok 模型读取 frames-manifest.json 及 JPEG
    → 结构化视觉筛查建议
```

准备工具不加载模型 profile，不读取 API key，也不访问网络；要求源 hash 一致。
默认 4 FPS，允许 1–8 FPS、最多 64 帧，原视频限制仍是 12 MiB / 30 秒。
每次保存独立源快照和全帧 JPEG（最长边 768），帧时间来自解码后相对起始 PTS，
不是模型估计时间，也不是 FPS 滤镜生成的伪时间轴。超预算拒绝，不静默少抽。
调用者先读清单，再读列出的图片；记录工具成功返回的图片数量，不能只报自称覆盖率。
这仍是远端模型推理，CLI 读取图片会将图片作为模型上下文发送，需已有素材外发授权；
「无需独立 xAI key」不等于免费、不走网络或只在本机推理。

声轨未进入此通道，ASR 也没有在本次新工具中实现。只能做外观 / 场景 / 穿帮嫌疑筛查，
不能证明台词、声纹、连续口型或同念；人审 / L2 / registry 门不变。

原生 xAI 调研：官方 [图片理解](https://docs.x.ai/developers/model-capabilities/images/understanding)
支持 `input_image`；[语音转写](https://docs.x.ai/developers/model-capabilities/audio/speech-to-text)
是独立 `/v1/stt` 接口；本次没有找到联合带声 MP4 理解契约。
`grok_provider.py` 仅保留未接入 MCP 的可选图片请求 / 响应原型及离线测试，
`h3-grok-screen` profile 仅作非秘密配置样例，**没有实时请求、未验证可用性、不作为当前执行入口**。
没有将 Cursor 登录凭据转换或提取为 xAI API key。

Grok CLI 已完成 26 张 JPEG 的真实 Read 及结构化回答，约 139 秒，
详见 `2026-10-23-grok-cli-visual-screen.md`。仍无声音，不能据此完成 L2。

## 验证记录

- 新增核心测试 36 项 + SDK 实际工具调用测试 1 项：37 passed。
- SDK 测试在 `uv --no-project --isolated` 环境执行，不以跳过 MCP 测试冒充通过。
- 原词面/registry 证据门回归：使用原 `.worktrees/feat-orch/.venv`，20 passed。
- 首次在根 `.venv` 跑旧回归有 3 项缺 `impacket`，没有改测试规避，改用原有完整环境重跑。
- 静态：Python 编译与 `git diff --check`。
- `cursor-cli mcp list-tools h3-av-review` 确认 3 个工具。
- Cursor CLI 以 `grok-4.7-medium` 实际调用 status/inspect，各一次；返回 missing key 与
  6.416667 秒 MP4 的真实 hash/参数；没有调用上传工具。
- 原始 CLI 回执：`runs/visual_qc/av-mcp-setup-20261023/cursor-smoke.jsonl`。
- 原生 Google 请求目前仅有 mock 协议测试，**没有真实 API 调用/质量验收**。

接入调试记录：旧 CLI 不展开工作区变量，首次失败启动曾触发根 `.venv` 的项目同步
（3 个包重新安装）；该次生成的根 `uv.lock` 已移除，未擅自回滚环境。
修正后的启动命令显式使用 `--no-project --no-env-file`，SDK 在 uv 的脚本缓存环境隔离运行。
没有改动出片所用的 `.worktrees/feat-orch/.venv`。

参考：[Cursor CLI MCP](https://prod.cursor.com/docs/cli/mcp)、
[官方 Python SDK](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)、
[Gemini 视频输入与采样](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding)。
