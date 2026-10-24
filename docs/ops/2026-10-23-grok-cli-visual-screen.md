# Grok CLI 无独立 API key 的视觉筛查实测

结论：**复用当前 Cursor CLI 的 Grok 已能读图并输出视觉筛查报告，无需独立 xAI key，
不操作网页；这不是连续音画审核，也尚未验证批处理效率或准确率。**

## 本轮实际链路

1. 本地 `ReviewService.prepare_visual_clip` 生成密帧及 `frames-manifest.json`。
   同一能力通过项目 MCP `av_prepare_visual_clip` 暴露，工具发现已验证。
2. 从项目根启动已登录的 Cursor CLI，选择 `grok-4.7-medium`，ask 模式、sandbox enabled。
3. 仅允许读该清单与列出的 26 张 JPEG；禁止 MP4、浏览器、搜索、外部审核 API 和写文件。
4. CLI 真实 Read 回执核实 26 张图片全部返回 data blob；模型输出另行校验，不只信自报数量。

本次本地准备由直接调用 service 完成；真实 CLI 测试验证的是 **Read 清单和图片**，
没有声称 CLI 在本次试验中调用了新增的 MCP 准备工具。新增工具的实际媒体路径由本地测试覆盖。

凭据：`XAI_API_KEY`、`GROK_API_KEY` 均未设置，没有提取 / 复用 Cursor 登录令牌。
推理走已有 Cursor 模型通道，可能消耗该通道额度；不是完全离线，也不是免费承诺。
密帧读取会将图片交给远端 Cursor 模型，本次使用此前已授权外发的同一短片。

## 素材与结果

- 输入：前次 EP01-U01 派生片 `sample-k7.mp4`，6.416667 秒。
- SHA256：`eb922ba43447919e0f097c760590054f3e722c40976325e336942408a2528d08`。
- 本地帧：4 FPS，26 张，0.0–6.25 秒；最长边 768，保留全帧上下文。
- 时间：来自实际选中帧的相对 PTS，不由模型猜测；源文件及各 JPEG hash 已复核。
- Cursor 最终回执 `duration_ms=139297`，exit 0；这是一例，不是批处理基准。
- 成功结果：`VISUAL_OBSERVED`，26 张 Read 成功，无图像输入错误。
- 模型能细述戒盒合上、手指指向戒指，以及 4 秒附近人物近景切换。
- 模型明确保留 `AUDIO_UNAVAILABLE` 和 `UNVERIFIABLE`，没有生成对白或证明同念。

模型提出「窗外吊灯样物体空间异常」及「叠手处手指边界不清」两项嫌疑。
它们均**未定案**；反射、透视和正常手部重叠都可能造成误报。
本次没有人工连续带声真值，不报缺陷识别准确率；新增人工完整实看数仍为 0。

## 证据与离线复验

证据根：`runs/visual_qc/av_mcp/20261023T141338Z-a42e1e3ecd74/`。

- `source.mp4`：已验证 hash 的只读源快照；原素材没有改动。
- `frames/`、`frames-manifest.json`：逐帧时间 / hash / 输入边界。
- `cursor-grok-probe.jsonl`：CLI 原始回执，仅本地保存，不输出完整推理内容或图片载荷。
- `cursor-grok-probe.stderr`：空。
- `cursor-validation.json`：实际 Read 覆盖、最终答复与边界校验。
- `verify_cursor_result.py`：只校验本地证据，不重新请求模型。

```bash
python3 runs/visual_qc/av_mcp/20261023T141338Z-a42e1e3ecd74/verify_cursor_result.py
```

本轮 AV/MCP/密帧单测 50 passed（含真实本地 ffmpeg 抽帧和 SDK 调用），
原 dialogue / registry 回归 20 passed；编译、skill 校验与 `git diff --check` 通过。
没有修改 NAS、登记 registry、触发重渲、提交或推送 Git。

## 后续执行方式

给其它 CLI agent 的最小提示：

```text
使用项目 h3-av-review 的本地工具，不调用 av_review_clip，不操作网页。
对我授权外发的短片先 av_inspect_clip，取得 SHA256，再 av_prepare_visual_clip，fps=4。
不要因为 av_review_status 提示缺 Gemini key 就中止：本地准备不需要它。
读取返回的 frames-manifest.json 及全部列出的 JPEG，核实实际图像工具成功数。
按源时间列出画面事件、嘴部可见性及穿帮嫌疑；只记模型筛查，不作人审签字。
这里没有声音，不生成对白或声纹结论，不因开口认定同念；口型必须 UNVERIFIABLE。
超过 64 帧预算时先缩短片段，不静默减采样。不可读图片时停止，不编造观察。
```

实际媒体路径由执行者代入，不默认授权其它 U 或整集外发。
若 ask 模式拒绝本地写出准备产物，可以先在本地调用准备器，再让只读 agent 读取既有清单；
不要为通过限制而全局放开权限。

下一步可评估分镜级抽帧复用、带时间标注的导航拼图减少 Read 往返；须保留原密帧用于
局部核查，不以缩图导致嘴部 / 手部不可见换取表面提速。ASR 接入和密帧融合仍未在新工具实现，
即便接入也须标成 ASR 文本辅助，不伪装原生连续音画。完整 L2 仍未完成。
