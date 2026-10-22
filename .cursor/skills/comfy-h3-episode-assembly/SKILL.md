---
name: comfy-h3-episode-assembly
description: >-
  Assemble a full episode from generated H3 unit clips: word-anchored
  rough cuts, seam handling for motion-latent chains (frame matching,
  speaker-aware J/L split edits, histogram shot matching), loudness
  normalization, and merged episode subtitles. Use when the user asks
  to 拼接/组装/粗剪 a whole EP from unit outputs, when episode assembly
  seams look obvious （拼接明显/掉帧/拖影）, or when planning how
  generated units will be edited together.
---

# Episode Assembly（整集组装与接缝处理）

把一个 EP 的全部单元（U）按剧情顺序剪成一集：剪掉对白前后的空白和
多余画面、处理单元间接缝、统一响度和色彩、输出整集字幕。工具是
`scripts/assemble_episode.py`；本 skill 是它的使用规程和接缝诊断手册，
规则来自 2026-10-22 潮缚 EP24 的 v1–v5 对比测试与寿命掮客 EP01 验证。

## 先说清三条铁律

1. **禁止用叠化/淡化混合帧盖接缝。** 实测产生重影拖影，观众更出戏；
   跨切点补帧（RIFE/FILM）同理禁用。接缝靠选点和声音，不靠混合。
2. **音画必须分开定点。** 音画锁死同点切是接缝显形的头号原因。
   对白缝用 J/L cut（见下），这是专业对白剪辑的主流做法。
3. **剪辑修不了生成状态错误。** 人物站位、机位轴线、服装在缝两边
   不一致时，剪辑只能缓解；定案走坏缝补生成或改生成契约，不要在
   组装参数上无限打转。

## 输入与前置条件

- 输入目录：子目录即单元，内含 mp4（优先 `*-audio.mp4`)、
  `prompt_h3.txt`、`run_meta.json`；飞牛 `<EP>/<U>-WENXI/` 布局或
  本地 verify 缓存布局都可。
- 每单元需要词轨与镜头切分点：有 `candidate_audit.json` 直接用；
  没有则工具自动用 faster-whisper + ffmpeg 场景检测计算并缓存
  `assembly_audit.json`（需 feat-orch venv，`PYTHONPATH=src`）。
- 组装前单元应已过对白审核（见 comfy-h3-dialogue-check）；带
  `EDIT_NOTE.txt` 的放宽条，其剪辑点先在单元层落实或在 manifest
  里人工指定，不要指望组装器猜。
- 同集只拼同一链的定版（原工作流/文戏不要混拼；规格虽一致，
  观感与 latent 谱系不同）。

## 运行

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
PYTHONPATH=src .worktrees/feat-orch/.venv/bin/python \
  scripts/assemble_episode.py \
  --episode-dir <单元父目录> --episode EP24 --out-dir <输出目录>
```

产物：`<EP>_assembled.mp4`、`edit_manifest.json`（每条缝的分类、
切点、依据）、`<EP>_assembled.srt`（按音频放置重定时的整集字幕）、
`qc.json`。**先审 manifest 再看片**：缝的时间点清单要随测试片一起
给用户，用户报"第几条缝"时能直接定位。

## 组装规则（已验证，勿随意改）

### 基础粗剪

- 有对白条：入点 = 首词 − 0.35s；出点 = 末词 + 0.5s，若 1.0s 内有
  镜头切分点则顺延到切点 + 0.1s。
- **独立开场条**（集首或 continuity=independent）：入点最多剪
  0.5s，保住新场景的建立画面。
- 无对白条：整段保留（纯动作条暂无可靠自动裁点，不要用静音
  检测硬剪；H3 的"空白"是慢动作+环境底噪，不是黑帧或纯静音）。

### 接缝分类与声音提前量

接缝分三类，处理完全不同：

| 缝型 | 判定 | 视频入点 | 声音 |
|---|---|---|---|
| 换场缝 | 下条 independent | 原点硬切 | 同点，50ms 级微淡 |
| 同人同框 | 下条首句说话人 == 上条尾镜主体 | 帧匹配点，但 ≤ 0.15s | 提前 ≤ 0.15s |
| 听者尾巴/换说话人 | 其余对白链缝 | 帧匹配点，夹在 0.30–0.50s | 提前 0.30–0.50s |

- 接力（motion_latent）条的开头约 1 秒是上一条尾部的重生成，
  在这段里逐帧找与上条尾帧最接近的帧作视频入点（搜索窗 1.2s，
  每跳 1 秒罚 6 灰度级防过度跳）。
- 音频独立放置：对白条音频从本地 0 秒起播，画面切入时音频本地
  时间恰等于视频入点（口型同步），切点之前听到的就是 J-cut
  提前量；上条音频留 0.12s 环境尾（L-cut），两端 20/120ms 淡化。
- **提前量为什么分档**：同人同框时声音提前 0.5s 观众会听出
  "声音比人物先动"（EP24 缝 1 实测）；听者尾巴时 0.3–0.5s 是
  经典 J-cut（先闻其声、再见其人），反而自然。说话人与尾镜
  主体从 prompt 的 ▲ 镜头行与台词归属解析（注意：镜头主体
  可能是听者，说话人以"口型同步开口"所在段落归属为准）。
- 帧匹配可能不命中（寿命掮客批的接力头在 0 秒即最优）：此时
  只靠 J-cut 与调色，不要强行跳帧。

### 色彩与响度

- 同场景单元按黑点/白点逐通道直方图匹配（p5/p95，55% 力度），
  基准条自动选离场景中值最近者。只补平均亮度不够，相邻条
  平均亮度可差 30%，黑白点和白平衡才是跳眼主因。
- 整集两遍 loudnorm 到 −14 LUFS / −1.5 dBTP，音频统一 48 kHz；
  源素材响度可差 4 dB、真峰值能到 +0.3 dBTP，不统一必爆。
- 接缝处强制关键帧；全程严格 CFR 24 fps 时间戳重建。
  （注：源素材本身是满 24 fps，"掉帧感"从来不是丢帧，
  是接缝处运动相位与底噪的断裂，不要去查编码丢帧。）

## QC（每集必做）

1. 整集 ASR 复核：全部期望台词在位（注意金额/数字的 ASR 写法
   差异，如 `$13.40` vs "thirteen dollars"，不是缺句）。
2. 响度复测落在 −14 ± 0.5 LUFS、TP ≤ −1 dBTP。
3. 抽每条缝前后帧：必须是干净单帧（无重影）、无黑帧。
4. 把缝时间点清单（manifest 的 `seam_times_s`）发给用户逐条
   对照反馈；反馈只改对应缝的分类/提前量，**一次只动一个
   变量**（v1–v5 的教训：同时改多处无法归因）。

## 接缝问题诊断表

| 症状 | 大概率原因 | 处理 |
|---|---|---|
| 声音比人物先动 | 同人同框缝提前量过大 | 提前量压到 0.15s |
| 缝处生硬、像幻灯片 | 音画同点切、无提前量 | 给 0.30s J-cut（跳帧保同步） |
| 重影/拖影 | 用了叠化或跨切补帧 | 全部去掉，改硬切 |
| 亮度/色温一跳 | 只补了平均亮度 | 直方图黑白点匹配（本 skill 规则） |
| 咔哒/底噪突变 | 音频硬切 | 微淡化 + 上条 0.12s 环境尾 |
| 以上都做了还跳 | 生成状态不一致（站位/机位/服装） | 坏缝补生成，或认了换切点绕开 |

## 剪辑解决不了、要回生成端的事

以下情况不要继续调组装参数，直接升级处理：

- 缝两边人物站位、视线、持物明显对不上：用首尾帧生成一段
  1–2s 桥接镜头，或生成反应/插入镜头盖缝（只救最差的缝）。
- 某条内部有双人同念、地理镜像等画面错误：回该条的修复
  流程，组装层最多整段弃用坏拷贝。

## 给未来生成的接缝契约（拆包/生成时执行）

主流 AI 短剧流水线（分镜生成 + 尾帧接力/续写二选一）与专业
剪辑共同指向：接缝要在生成时设计，不要事后补救。

- 单元边界落在完整台词或完整动作结束处，不按固定时长硬切。
- 同场景下一条直接从新机位/反应镜头/动作中开始，不要在
  成片里保留"重生成上一条尾巴"的画面（那是 latent 交接的
  内部机制，剪辑时应被帧匹配吃掉）。
- 每句台词前留 0.3–0.5s 无台词把手，给 J-cut 和选点留空间；
  现在的包台词从 0.0s 开始是接缝被动的主因。
- 每场多生成 1–2 个无对白反应/插入镜头作剪辑救生圈。
- 只有真正不能打断的长镜头（唱段、缓慢推近）才用视频续写/
  latent 续接；普通对白按分镜独立生成、硬切组装。

## 已知边界

- 无对白动作条只能整段保留，自动裁点不可靠。
- 帧匹配是灰度级近似，景别差异大时（近景↔全景）数值参考
  意义有限，最终以缝帧目检为准。
- EP 级规范（片头卡、剧名、音乐、转场惯例、交付尺寸如
  1080×1920）尚未定义；本 skill 只负责剧情粗剪，交付包装
  另定。源素材 768×1376 不是精确 9:16，交付前需确认裁切
  还是补边。
- 测试片先放飞牛 `<批次>/<EP>-整集组装测试/` 与定版分开，
  用户确认后再进正式目录。

## 参考

- Adobe，J/L cut 说明：声音连续是藏切点的第一手段
  https://www.adobe.com/creativecloud/video/post-production/cuts-in-film/l-and-j-cut.html
- MiniMax H3 官方：首帧/尾帧/首尾帧与参考生成
  https://platform.minimax.io/docs/guides/video-generation
- ArcLoop：H3 片段拼接三路线（续写 / latent 拼接 / 分镜剪辑）
  https://arcloop.ai/handbook/zh-CN/minimax-h3-clip-chaining-longer-videos
- Blackmagic 调色指南：hero shot 与镜头匹配顺序
  https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Colorist-Guide.pdf
