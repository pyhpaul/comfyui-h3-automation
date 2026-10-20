---
name: comfy-h3-dialogue-check
description: >-
  Batch-verify dialogue in already-rendered H3 mp4s without watching them:
  extract audio, ASR (faster-whisper), score against the pack's （） lines,
  emit a bilingual EN/中文 report plus per-video SRT files that 剪映专业版
  can import onto the subtitle track. Use after a batch lands (local or
  Feiniu), when the user asks to check 台词/对白, or to prep review files
  for 剪映. Not for who-spoke/lip-ownership checks — those stay visual.
---

# Dialogue Check（成片对白批量核对）

## What this does

成片没有分轨人声，H3 出的是混合音轨。核对路径是整轨抽出 → 转写 → 与剧本对：

1. `ffmpeg` 抽音轨成 16k 单声道 wav（`comfy_orch.dialogue_gate.mp4_to_wav`）
2. `faster-whisper`（small, CPU int8）转写，带段级时间戳
3. 与 `prompt_source.txt` 里全角 `（）` 的期望台词打分
   （`extract_expected_dialogue` + `score_transcript`）：
   台词缺失 / 多说 / 该沉默却开口 / 重合度
4. 产出：一张判定表 + JSON 报告（转写原文、中译、段级时间戳）+ 每条同名 `.srt`

人只需要看 FAIL 行的转写文本；文本含糊时才去听那几秒。不要逐条开片。

## Run

```bash
cd /home/linux_dev/projects/comfyui-h3-automation
export PYTHONPATH=src PATH="$PWD/.worktrees/feat-orch/.venv/bin:$PATH"

python scripts/ops/batch_dialogue_check.py \
  --video-root jobs/wenwu_ab_test/wuxi_orig \
  --job-root jobs/ep_units_wenwu_test \
  --prefix EP17='EP17-兽王降临-wenwu' --prefix EP18='EP18-秘银碎裂-wenwu' \
  --report runs/dialogue_check_<batch>.json \
  --emit-srt --zh-map runs/zh_map.json
```

- `--video-root`：`rglob("*.mp4")`，文件名须是 `<EP>-<U>.mp4` 形状。
- `--prefix EP=job前缀`：用来在 `--job-root` 下定位 job 目录读 `prompt_source.txt`。
- `--emit-srt`：在每个 mp4 旁写同名 `.srt`（UTF-8）。
- `--zh-map`：可选 JSON `{英文期望台词: 中译}`；命中的转写段会在 SRT 里
  追加一行中文，并供双语报告引用。没有映射时 SRT 只有英文转写。

16 条 12 秒片子 CPU 约 100 秒。`faster-whisper` 在 feat-orch venv 里；
Whisper 模型首次用会下载 small。

## Report format（给人看的双语版）

在 JSON 之外，按 `runs/dialogue_check_bilingual.md` 的样式出一份双语 md：

- 开头先写「怎么读」：真对白问题（需处理）与工具误读（非语音被误听，
  无需处理）分开，别让读者把标红当成片子出错。
- 有对白的条：期望（英 + 中译）→ 实际听到（英 + 中译）→ 判定。
- 无对白条被误听出的英文：标题写「工具误读留痕（不是台词错误）」，
  列表格给原文 + 实际声音性质（兽吼 / 呻吟 / 剑风 / 撞击），
  不要用「胡话」「FAIL」作标题吓读者。
- 单独点名「台词重复说」：比对按词覆盖算 PASS，重复（如先后蹦词再整句重来）
  只有看转写才发现，必须在报告里明说。

中译由当前 agent 直接翻（台词量小），不要为此接外部翻译 API。

## 剪映导入

- `.srt` 给**剪映专业版（电脑版）**：视频拖上时间轴后，
  「文本 → 新建文本 → 导入本地字幕」（或「AI字幕 → 新建字幕 → 导入文件」），
  支持 SRT/LRC/ASS，必须 UTF-8。手机版多数版本无此入口。
- 抽出的 wav 也可直接导入音频轨，与字幕轨贴着波形核时间。
- SRT 时间是转写段起止，个别词与口型可差小半秒：核内容够用，逐字对口型不行。

## Known limits（先说清，不要过度承诺）

- **只核「说了什么」，不核「谁说的」。** 两人同念一句（口型串音）ASR 发现不了；
  对话条仍需按既有政策抽 1–2 条看动态嘴部。锁嘴改动在转写层无差别。
- **非语音会转成胡话**：兽吼、呻吟、剑风、撞击 → 英文幻觉词，FAIL 里占多数，
  看中译/原文即可排除（典型：`One golem fey funder…`、呻吟转 `I'm dead!`）。
- **资产码污染**：某些包的参考设定里有 `（W-LIAM-04）`、`（scene-035）` 这类
  全角括号资产码，会被提取器误当台词。批量脚本已用 `_ASSET_CODE` 正则先剥掉；
  新包型如果码格式不同，先查报告的 `expected_lines` 是否干净再信判定。
- **耳语/含混台词可能漏转**；人名拼写差（如 Vane→Vayne）属正常，不算错误。
- 该沉默的条若期望提取为空集，按 `BAD_extra` 路径判：有词即标红，
  再由人看转写区分真开口和幻觉。

## Relation to the queue-time gate

- 本 skill 是**出片后**的批量事后核对（便宜、默认可跑）。
- `scripts/run_ep_units_profiled.py --dialogue-gate` 是**入队时**的门（带重试烧卡），
  按仓库规则默认不开，只在用户点名或抽查发现读错时用（见
  `docs/ops/2026-10-17-dialogue-gate-burn-avoidance.md`）。
- 两边共用 `src/comfy_orch/dialogue_gate.py`；改打分逻辑时同步跑
  `tests/test_dialogue_gate.py`（15 条）。

## Files

- `src/comfy_orch/dialogue_gate.py` — 抽音轨 / 转写 / 期望提取 / 打分（+ 种子偏移重试工具）
- `scripts/ops/batch_dialogue_check.py` — 批量驱动、JSON 报告、SRT 导出
- `tests/test_dialogue_gate.py` — 打分与提取的回归测试
- 首批实测：`runs/dialogue_check_wuxi_{orig,opt}.json`、
  `runs/dialogue_check_bilingual.md`（runs/ 不入库，为本地样例）
