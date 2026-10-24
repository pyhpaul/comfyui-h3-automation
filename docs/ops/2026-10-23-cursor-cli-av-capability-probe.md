# Cursor CLI 音画输入探针（2026-10-23）

结论：**模型切换成功；本机这版 CLI 的内置 Read 路径拒绝 MP4，未进入音画审核。**
不能由此断言供应商原生模型不支持音画，也不能比较三个模型的口型审核准确率。

## 范围与素材

- CLI：`cursor-cli`，版本 `2026.10.19-6bbf2c4`；使用现有登录，没有读取或复制凭据。
- `cursor-cli --list-models` 实时确认下列三个 model id 可选。
- 原片：`runs/visual_qc/lihun-EP01-EP03-20261023-l1-l3-pilot/media/EP01-U01.mp4`。
- 从原片 3.2–9.6 秒生成独立 6.416667 秒测试片，不覆盖源文件。
- 测试片保留 768x1376 / 24fps H.264 和 32kHz AAC 声轨，ffmpeg 完整解码无错误。
- 输入不提供台词、剧情、人物名或旧审核结论。三个全新 CLI 会话使用同一提示词、同一文件，
  仅改变模型；`--mode ask --sandbox enabled`，每次超时上限 180 秒。
- 提示要求只读该 MP4，禁止 shell/ASR/抽帧/网络/MCP/委派；日志实际各仅一次 Read 调用。

## 结果

| 请求 model id | CLI init 回报模型 | CLI 回报执行时长 | 音画输入结果 |
|---|---|---|---|
| `gemini-4-argon-medium` | Gemini 4 Argon Medium | 16.085s | INPUT_UNSUPPORTED |
| `grok-4.7-medium` | Grok 4.7 256K Medium | 14.096s | INPUT_UNSUPPORTED |
| `gpt-5.4-medium` | GPT-5.4 272K Medium | 14.140s | INPUT_UNSUPPORTED |

时长为 CLI result 内的 `duration_ms`，不代表含启动的端到端耗时，不据此作性能排名。
三个实际 `readToolCall.result` 均为：

```text
Cannot read binary files of type mp4
```

三个模型均如实返回未取得声音/画面，没有编造台词或口型结论。
CLI exit code 均为 0、result 为 success，只代表流程正常结束，**不是媒体能力或审核通过**。

本测试证实的是此版本、这些模型、此调用方式的文件读取限制；未验证其它 Cursor 产品界面、
潜在附件入口、供应商原生 API，也未测抽帧+ASR替代流程。受阻后未继续跑静音/错位变体：
相同输入适配器未交付媒体，继续做模型效果对照没有意义。

## 证据与重放

本地证据根：`runs/visual_qc/cursor-av-probe-20261023/`。

- `inputs/clip-a.mp4`：唯一媒体输入。
- `inputs/probe-prompt.txt`：同一盲测提示词。
- `{gemini,grok,gpt}-stream.jsonl`：CLI 原始事件，包含模型 init、实际工具错误、最终结果。
- `{gemini,grok,gpt}-stderr.log`：三份均为空。
- `summary.json`：结构化探针结果、模型回执、输入/日志 hash、原片区间和媒体参数。
- `summarize_probe.py`：检查三份日志、工具范围、结果及输入 hash，可重跑生成汇总。

原片 SHA256：`b0610bf1514ba3285014527ef6c3182f13da8499bd5d1e3f0049659afd4c1a2b`。
派生测试片 SHA256：`eb922ba43447919e0f097c760590054f3e722c40976325e336942408a2528d08`。
结束后重算原片 hash 一致；未改 NAS、fix_registry 或历史审核记录。
媒体和 CLI 原始日志仅本地保留，未加入 Git 或推送；本文件不包含原媒体内容。

从 `inputs/` 目录可按下列形式重放（会调用付费/订阅模型，不是离线验证）：

```bash
cursor-cli --model gemini-4-argon-medium --mode ask --print \
  --output-format stream-json --sandbox enabled --trust \
  --workspace "$PWD" "$(<probe-prompt.txt)"
```

离线验证与汇总：

```bash
python3 runs/visual_qc/cursor-av-probe-20261023/summarize_probe.py
```

## 对实现方案的影响

1. **Cursor CLI 继续负责 agent 编排和结果解释，不能仅靠 `--model` 增加输入模态。**
2. 真正音画审核需要另接可验证的媒体适配器：通过本地工具/MCP调用原生音画接口，
   向模型送带声 clip、返回时间定位与证据。不是让 CLI 把 MP4 当文本读。
3. 接入前核对服务输入格式、采样、数据保留及 profile；本次没有接入外部原生 API。
4. 适配器能实际交付音画后，才执行静音/换画面/时间偏移对照与真实坏例校准。
   抽帧+ASR仍可用于筛查，但不能冒充这一能力验证。

验证：三次 CLI 均正常退出；离线汇总 3/3 断言通过；测试片解码通过；原片 hash 未变。
**未完成项：音画感知、说话人/同念效果评测、任何模型准确率结论。**
