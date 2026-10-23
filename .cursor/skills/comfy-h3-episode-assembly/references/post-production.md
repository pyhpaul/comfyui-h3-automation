# 完整后期与 v2 试片复现

执行完整 EP 后期、字幕/BGM/尾卡，或复现试片时读取。
以下区分已实现能力与执行要求，不把样片特例当作通用参数。

## 1. 资源与入口预检

项目根目录下的现有资源：

- 正式代码：`scripts/episode_post/`；环境见该目录 README。
- 相关测试：`tests/test_ep_pilot*.py`。
- 已导出成片：`outputs/ep-post-pilot/EP01-v21-v2-final/`。
- v2 输入：`.cache/ep_post_pilot_v1/pilot_input_v2.json`。
- 原视频：`assets/episode_post/local/pilots/lihun-v21-ep01/units/U01-WENXI/` 至 `U04-WENXI/`。
- 词轨：同一 pilot 目录的 `analysis/`，每份记录源 SHA256。
- 音乐：同一 pilot 目录的 `music/sb_undertow.mp3`。
- 已认可 ending：`assets/episode_post/endings/bloom-hold-suspense/v1/preview.mp4`。

代码、测试、方案及认可样片随 Git 分发；原剧集、原曲和本地基底在被 Git
忽略的 `assets/episode_post/local/`，缺少时须按项目资产清单恢复。
首次运行先做 `python scripts/episode_post/verify_project_assets.py`；
需要原片重放时加 `--include-local`。清理研究 worktree 不影响正式入口。
不得自动下载替代音乐或回退旧粗剪器，不能声称缺少私有源片也能重建整集。

运行前检查 `ffmpeg`、`ffprobe`、字体、libass/drawtext，以及 Python 环境的
`numpy`、`pytest`、`faster_whisper`；转写还需要已缓存 Whisper small。
以下命令从仓库根运行，实际 Python 环境须先验证：

```bash
PY=.venv/bin/python
PILOT=scripts/episode_post
"$PY" "$PILOT/run_ep_post_pilot.py" --help
"$PY" -m pytest -q tests/test_ep_pilot.py \
  tests/test_ep_pilot_music.py \
  tests/test_ep_pilot_audio_qc.py \
  tests/test_ep_pilot_creative.py tests/test_episode_post_assets.py
```

## 2. 输入计划与版本保护

试片 runner 接受 JSON manifest；按实际 schema `ep-post-pilot/v1` 使用：

- `sources`：每 U 的 `path`、`sha256`、`prompt`、`prompt_sha256`、
  `analysis`、`meta` 和归档身份。
- `clips`：按剧情顺序排列的 `unit`、`in_frame`、`out_frame`、`reason`。
- `fps`、`width`、`height`、`endcard_frames`。
- `subtitle_language`、`subtitle_aliases`、`subtitle_style`。
- `music`：源 path/hash、来源/许可/署名、增益、`cues`。
- `source_version`、`revision`、`review_notes`、`change_notes`。

v3 已实现 `protected_ranges` 的帧区间保护检查及 `ending_push` 的轻推近；
创作语义仍由 agent 审查。通用转场配置、通用 EP 参数不是已落实功能，
不能添加未消费字段就声称生效。试片 JSON 的 `audio` 部分参数仍是说明性值，
渲染仍硬编码 -18 LUFS staging / -16 LUFS final，不能只改 JSON 改目标。
`schema`、`episode`、`subtitle_language` 也不是严格校验或行为切换入口；
这些字段不能使固定 EP01 / 英文实现自动适配其他集或语言。

审核输入计划后再运行。不要用渲染输出的 manifest 替换原始计划而丢失
变更依据。每次修改使用新输入文件和新输出目录；旧源、旧片、旧证据不覆盖。
这里的计划审核由 agent 自检执行，不默认等待人工签字；用户在推荐成片
审核后再决定是否修改。创意选择见 [Agent 主导创作](agent-direction.md)。

## 3. 字幕

- 以规范剧本原文对齐实际词轨；保留原始 ASR，明确记录名字等识别别名，
  不能用宽松同义替换掩盖缺词、错句或说话人错误。
- 同一条保留多个片段时逐段重映射；整句跨删除区间应阻止渲染，不能
  静默截断、补写或让字幕漂移到另一段对白。
- 英文短句，最多两行，语义换行、不压脸和嘴、留底部平台安全区。
  v2 原生画幅使用 DejaVu Sans 38px、2px 描边、约 170px 底边距；
  新分辨率按视觉比例重新检查，不盲抄像素。
- 输出 `EP01.en.srt`、`EP01.en.ass`、诊断用 `EP01.words.srt`，以及中文词轨
  `EP01.zh.srt` / `EP01.zh.ass`（与英文字幕同时间轴；文案来自计划
  `zh_captions`，或剧本里 `English.（中文）` 双语句）。
  逐词英文文件不等于最终字幕样式；审核实际烧录画面及手机宽度可读性。
- 可读性延长用 `subtitle_style.end_overrides`，语义换行用 `line_breaks`；
  不得覆盖下一句、缩掉原对白或借换行改词。
- v2 两处已知跨镜停留约 0.108s / 0.35s，属于可读性取舍，不应复制到
  其他 EP；新片逐句检查，不把这些时码当模板。

## 4. BGM 与混音

- agent 先分析剧情节拍、情绪和强度曲线，自行选择音乐、段落、留白与
  切换点；同主题不同强度优先，情绪确有转向时可换曲，不强制只用一首。
  选择应基于实际试听与素材证据；无法试听时披露限制，不宣称最佳听感。
- 先按剧情标 cue，再选素材。不开场铺满、不每镜换音乐，允许对白和
  现场声独立承担情绪。音乐切入/退出落在叙事与乐句上，而非机械踩点。
- 试片使用 Scott Buckley 的 Undertow；路径、hash、曲名、作者、原始
  来源、许可 URL、修改说明保存在 manifest 和 `MUSIC_CREDITS.txt`。
  沿用须核对资产身份与所需署名；换曲/联网获取按联网 skill 执行。
- cue 明确 `start`、`end`、`source_in` 和理由。EP01 的 21-32s、44s-结尾
  只适用于本集；`source_in=57s` 不是通用推荐位置。
- 试片音乐基准约 -29 LUFS，对白区再降 9dB；平滑包络提前约 80ms、
  释放约 350ms。值为试听起点，不是对所有曲目的固定规范。
- **master 不含配乐**：`*-master.mp4` 只保留对白与结尾 SFX；BGM 只进
  `*-review-en.mp4`（及 `MUSIC_CREDITS.txt`）。交付飞牛时两版都归档。
- **复用 v2 确定性方案**：每个 cue 独立渲染全长 48 kHz PCM，重建
  样本时间戳，再在样本域叠加并施加对白避让包络。
  不回退到未经回归的单滤镜图延迟/sidechain 混音。
- v1 曾出现第二段音乐落到片头、结尾没音乐；因此在混音 WAV 上用
  “混音减对白”验证：计划外残差为零、各 cue 和尾卡处确有音乐、总采样数
  正确，再核对最终 AAC 没导出错轨。
- 单元增益 staging 保护原声，之后对最终混音两遍 loudnorm；在编码后
  MP4 上复测 LUFS/TP，而不是只看滤镜预期值。

v3 的 cue 支持 `gain_offset_db`、`fade_in`、`fade_out`，逐段控制相对
全曲基准的增益和淡化；每条 PCM cue 独立检查窗口，避免重叠时相互遮掩。
底层已可指定 cue 的 `path`/`sha256`，但交付署名/尾卡仍固定单曲，
不代表多曲完整交付已就绪。多曲/SFX 方案须先完善授权、导出及 QC，
不能仅加曲名就声称已换曲。v3 推荐版仍使用同曲的不同段落。

## 5. 结尾与转场设计

先回答“这一集最后留下什么情绪/悬念”，再做包装。结尾优先顺序：
完整最后一句 → 动作完成 → 最终反应 → 短淡出 → 尾卡与音乐收束。

试片实现：末镜最后 6 帧（0.25s）淡出，接 30 帧（1.25s）深色尾卡，
约 4 帧淡入；暖白 DejaVu Serif 的 `TO BE CONTINUED` 配简洁集号。
音乐延续到尾卡并淡出，不插无意义长黑场，不额外加突兀音效。

这只是基线，不限制 agent 选择更合适的结尾。v3 已增加有界平滑推近，
通过 `ending_push` 指定末单元保留区间内的帧、放大比例和裁切权重。
受控虚影、背景柔化、独立音效尚需适配；选用前检查实际实现与输出，
不用先让人工挑参数，详见创作参考。

- 系鞋带与平静反应构成 EP01 的人物选择，不能为缩短时长删掉。
- 无结尾反应素材时，不凭空冻结人脸、慢放或添加桥接生成；先提出方案，
  记录素材限制。短尾卡不能补救剧情未完成。
- 声音去咔哒微淡、场景内硬切、场景转换和最终淡出不是同一规则。
- 用户最新要求尾卡不显示音乐署名小字。v4 设置
  `endcard.show_music_credit=false`；完整 credits 与发布说明保留，
  不把移除画面小字理解为删除音乐来源与授权信息。
- 用户认为 v3 的 3.5% / 1.25s 推近不明显；v4 改为 10% / 2s，
  全局49.416667-51.416667s。幅度不是新通用常数，必须审实际可感知度、
  人脸/动作裁切与画质，不能只看 manifest 里有动画参数。
- 原生画幅并非精确 9:16。1080x1920、裁切/补边、平台安全区、片头和
  英文剧名仍需独立确认，不默认拉伸、放大或自行翻译。

## 6. 复现已审 EP01 试片

先核对资产和输入 hash。`prepare_ep_post_pilot.py` 会以排他模式创建固定
试片输入，已有 v2 输入时不要重跑；该脚本固定四条源 hash，不适用新 EP。
新 checkout 已恢复私有素材、且尚无 v2 输入时，先执行
`"$PY" "$PILOT/prepare_ep_post_pilot.py" "$PWD" --revision v2`。

以下命令需在同一 shell 中设置上文 `PY`、`PILOT`，输出目录必须未存在：

```bash
OUT=outputs/ep-post-pilot/EP01-v21-v2-replay-20261022-01
"$PY" "$PILOT/run_ep_post_pilot.py" \
  .cache/ep_post_pilot_v1/pilot_input_v2.json "$OUT"
"$PY" "$PILOT/transcribe_ep_pilot.py" "$OUT/EP01-review-en.mp4" "$OUT/analysis"
"$PY" "$PILOT/verify_ep_post_pilot.py" "$OUT"
```

不要选已有 `EP01-v21-v2-final` 作输出。转写是英文 small 本地模型；
verify 也是固定 EP01，包含本例名字别名和音频锚点假设。
完成命令后仍须执行 QC 参考中的成片自检与剩余技术检查。
子 agent 审核默认关闭，仅在用户明确要求时执行，不作为固定交付门禁。

### v3 agent 推荐版入口

`prepare_ep_post_v3.py <仓库根>` 从已锁定 v2 输入生成 v3 计划，创建
`.cache/ep_post_pilot_v3/`，目录已存在则拒绝覆盖。v3 计划增加动作保护、
末镜 3.5% 平滑推近、两段分别测量的音乐增益/淡化及两处字幕出点修正。
已有输入时直接使用，不重复准备：

```bash
OUT=outputs/ep-post-pilot/EP01-v21-v3-replay-01
"$PY" "$PILOT/run_ep_post_pilot.py" .cache/ep_post_pilot_v3/pilot_input_v3.json "$OUT"
"$PY" "$PILOT/transcribe_ep_pilot.py" "$OUT/EP01-review-en.mp4" "$OUT/analysis"
"$PY" "$PILOT/verify_ep_post_pilot.py" "$OUT"
```

实际首版输出目录为 `outputs/ep-post-pilot/EP01-v21-v3-agent-directed/`，
不得拿它作为重跑输出。`creative_plan.json` 记录推荐理由与已落实参数；
是否可审片以该版本 QC 和执行 agent 的自检记录为准，不凭文件存在推断通过。
历史 `AGENT_REVIEW.md` 仍保留为该旧版审核证据，不是新版本必需产物。

### 换成新 EP 前必须适配

runner 的文件名、报告集号、尾卡、画幅/fps、剧本提取、音频目标仍有
硬编码；verify 还有固定分析路径、名字别名和首段词轨锚点。
先泛化这些入口并增加代表性回归，再对新 manifest 跑端到端。
别把本参考的操作流程误报为这些通用能力已经实现。
