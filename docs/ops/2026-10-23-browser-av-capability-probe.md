# 浏览器音画能力探针（2026-10-23）

结论：**Grok 网页端完成原声/静音两例，能在本对照中区分真实对白与全零声轨；
精细 L2 口型审核能力仍未验证。** Gemini 两个网页入口未取得有效媒体审核结果。
这与此前 Cursor CLI 的文件读取受阻不矛盾：入口不同，输入通道也不同。

## 1. 实际路径与边界

- 使用现有浏览器登录，在本次创建的新标签页操作；未打开历史对话。
- 原生 Gemini/Grok API 所需环境 key 不可用，未读取登录令牌或从其它工具提取凭据。
- 仅提交 6.4 秒试片，不发整集、prompt、参考身份图、原 ASR 或旧审核结论。
- Grok UI 显示 `Expert`；底层模型版本未由界面确认，**不标成已测试 Grok 4.7 原生 API**。
- 没有调用生成视频、改原片、NAS 写入、fix_registry 或自动重渲。
- 网页测试不等于可持续自动集成；后续生产接入仍建议明确接口和 profile。

## 2. 对照素材

原片：`runs/visual_qc/lihun-EP01-EP03-20261023-l1-l3-pilot/media/EP01-U01.mp4`。
选源片 3.2–9.6 秒，生成时长 6.416667 秒的独立片段。

本地证据根：`runs/visual_qc/browser-av-probe-20261023/`。

| 输入 | 处理 | 验证 |
|---|---|---|
| `inputs/sample-k7.mp4` | 原声 | 解码音频峰值约 0.9466 |
| `inputs/sample-m2.mp4` | 仅将音量归零，视频流复制 | 解码声轨全部为零，峰值 0 |

两份 H.264 视频包 SHA256 完全相同，均 768x1376 / 24fps；AAC 均为 32kHz 双声道。
因此本次主要控制变量是声轨，不靠改文件名或改画面制造差异。
提示词相同且不含预期台词，每例独立新对话，避免先看到原声后补写静音版。

原片 SHA256：`b0610bf1514ba3285014527ef6c3182f13da8499bd5d1e3f0049659afd4c1a2b`。
测试结束重新校验一致；派生媒体、哈希、提示词与原始网页回执保存在项目本地，未入 Git。
另有 Windows Temp 副本用于浏览器原生文件选择；不作为原始资产替代品。

## 3. Grok 的两例结果

### 原声版

- 返回 `audio_status=SPEECH_OBSERVED`。
- 在没有提供剧本/ASR 的情况下返回：
  `You brought it yourself? You really can't let go. He already chose me. You don't need an audience.`
- 文本与既有源 ASR/剧本一致。这里不是新人工试听标签，不能扩展成整体转写准确率。
- 能描述灰西装金发男子、白色纹理外套卷发女子，以及桌上的戒盒/戒指等可见内容。
- 将两组对白关联到上述两人的外貌，但本次没有人工连续音画真值，不能据此判归属正确。
- **自述限制**：画面为 1 秒间隔帧；音频内容来自系统提供的交错转写，非直接原始波形感知。
  这些是模型对自己输入的描述，不是已独立抓包验证的供应商管线事实。
- `lip_sync_assessment=UNVERIFIABLE`，没有冒充口型通过。

另有时间轴问题：四个转写段中两个 `start=end`（1–1 秒、4–4 秒），不能直接用作
精确剪辑或口型边界。正确台词文字不意味着时间轴合格。

### 静音版

- 返回 `audio_status=SILENT`、`heard_text=null`、`speech_segments=[]`。
- 保留对相同画面的描述，未从人物张嘴或原声剧情猜出对白。
- 报告 AAC、双声道、32kHz 且全段零振幅，与本地夹具验证一致。
- 同样将口型同步记为 `UNVERIFIABLE`，理由是仅有 1 秒间隔的离散帧。

### 可以与不可以下的结论

**可以**：该网页入口在这两个样例中完成了视频内容处理/声音有无区分，
不只是成功上传文件；可作为内容级筛查入口进一步探索。

**不可以**：宣称模型原生联合处理原始音画、逐帧连续观看、可靠识别双人同念、
达到 0.1 秒级时间精度、已经完成前三集 L2，或以两例推算生产准确率。
全程新增人工完整带声实看数仍为 0。

## 4. 其它入口

| 入口 | 实际状态 | 不作的推断 |
|---|---|---|
| Gemini App，界面选择 4 Argon | 选择 MP4 后附件持续 loading；一次发送点击后仍无模型答复 | 不据此认定模型不支持视频；阻塞原因未定位 |
| Google AI Studio，界面显示 Gemini 3.8 Flash | 文件选择器可读取本地 MP4，但没有确认附件进入 prompt；未点击 Run | 不当作已测 Gemini 内容效果，也未创建 API key/开通计费 |
| 原生 API | 当前无可用对应 key，未调用 | Cursor/网页登录不能直接当原生 API 凭据 |

Grok 每例只显式提交一次。初次界面显示工作结束却无正文，各对本次对话做了一次
reload、没有点击重新生成或重复提交，随后取得最终 JSON；该 UI 恢复现象也应记录为
网页自动化脆弱点，不据此推断后台重试或计费次数。
结束后已关闭本次创建的四个标签页，未关闭用户原有标签页；Gemini 模式选择恢复为
进入时的 Flash。两条 Grok 测试对话未删除，其地址仅保留在本地回执中。

## 5. 证据与验证

证据根中的关键文件：

- `probe-prompt.txt`：盲测要求，不含台词或角色名。
- `fixture-validation.json`：视频包一致、声轨差异、媒体参数与源 hash。
- `grok-original-after-reload-settled.json`、`grok-silent-after-reload.json`：最终网页回执。
- `gemini-final-no-result.json`、`aistudio-final-no-media-confirmed.json`：受阻入口状态。
- `summary.json`：结构化结果，保留各模型的限制，不将自述状态直接视为通过。
- `verify_fixtures.py`、`summarize_results.py`、`browser_probe.py`：本次局部辅助脚本，不是生产适配器。

离线重验：

```bash
python3 runs/visual_qc/browser-av-probe-20261023/verify_fixtures.py
python3 runs/visual_qc/browser-av-probe-20261023/summarize_results.py
```

已验证：两例结构化答案可解析；原声文本匹配上述参考、静音不转写；两个口型结论均不可验；
时间段存在两处非正时长；源 hash 不变。脚本语法校验与 `git diff --check` 通过。

## 6. 下一步

1. 本次结果定位为**内容级 smoke test**，不升级 L2/registry 状态。
2. 若要测精细 L2，优先接有明确声轨/采样契约的原生接口，实际验证可配置时序分辨率，
   而非只让模型口头说“看得更仔细”。当前需一个可用的原生音画 API profile。
3. 接通后再做已知时间偏移、画面互换、错说话人/同念坏例与正常对照；
   没有真实坏例与人工完整标签前，不开放自动通过。
