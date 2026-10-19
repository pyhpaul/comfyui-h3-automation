# Dialogue-gate 烧卡规避（潮缚双线）

日期：2026-10-17  
批次：`潮缚（10.16）`  
编排：`/tmp/chaofu-dual-orch-v3.py` + `stuck-watch`

## 现象

单卡长时间停在同一 `Uxx` 上反复 `DIALOGUE_GATE_FAIL` → `SEED_BUMP` → 重抽，整集进度不动，租卡空转烧钱。

典型：`EP20-U05`、同类 `BAD_extra` 且 `overlap` 很高（0.8–1.0）。

## 根因（不是门禁误杀）

1. **对白本身常已说对**（ASR 能对上 `（）` 行）。
2. **说完后继续念乱语**：把后面无对白的中文画面说明念成英文胡话 → `BAD_extra`。
3. **旧编排放大损失**：同一份已接线的 `prompt_h3` 上连抽 5–7 次才回到编排改文案；改文案又只做笼统 strengthen，不对「尾段静音」下药。

门禁拦脏 latent 是对的；烧钱来自 **无效重抽策略**。

## 规避规则（必须遵守）

1. **门禁保持开启**（`motion_latent` 下）。关闸会更快，但脏 AV latent 会毒整条接力，更贵。
2. **Fail-fast**：runner `--dialogue-gate-retries` 默认按编排设为 **2**（最多 3 次 attempt），不要涨到 5–6。
3. **每轮 FAIL 立刻改提示词**（不要等 round≥3）：
   - `strengthen_unit`
   - `inject_whitelist`
   - 若 reason 含 `BAD_extra` / `BAD_missing_extra` → `harden_silence_after_dialogue`（说完后绝对静音 + 无 `（）` 的 ▲ 标禁读）
   - round≥2 或含 missing → `digitize_money_dialogue`（`seven hundred thousand` → `$700,000` 等）
4. **金额台词优先写数字形式**（`$700,000` / `$700 bucks`）：模型与 ASR 更稳；归一化已支持 word↔digit。
5. **不要**在同链上「先入下一条再异步门禁」；不要链头-only 门禁。
6. **卡住检测**：`stuck-watch` 看日志停滞 / 假 `queue=running`+history 已 success，自动杀该侧重启 resume，不靠“进程还活着”。

## 实现落点

| 项 | 位置 |
|----|------|
| Whisper CPU 单例 | `src/comfy_orch/dialogue_gate.py` `_get_whisper_model` |
| 数字归一化（含 seven hundred thousand） | 同上 `_normalize` |
| wait 轮询 2s | `scripts/run_ep_units_profiled.py` `_wait` |
| Fail-fast + 静音/数字化 FIX | `/tmp/chaofu-dual-orch-v3.py` |
| 假死拉起 | `/tmp/chaofu-orch-stuck-watch.py` |
| 进度 state | `/tmp/chaofu-orch/state/*.done` |
| 双线日志 | `/tmp/chaofu-orch/{A,B}-stdout.log` / `*-runs.log` |

## 推进口径

- 已 HANDOFF 的单元不重跑；按 runlog resume。
- 失败单元不跳过；用改提示词 + 少次数重抽推进。
- 飞牛批次名向用户要；成片只进飞牛。

## 2026-10-17 06:51 现场动作

- EP20-U05 / EP23-U05：金额数字化 + 尾段静音锁 + 白名单已写入 `prompt_source.txt`。
- A 旧编排（retries=5）已杀掉，改起 fail-fast `chaofu-dual-orch-v3.py`（GATE_RETRIES=2），从 EP23-U05 resume。
- B 保持 fail-fast，继续 EP20-U05。
- 状态快照：`/tmp/chaofu-orch/STATUS.md`；进度仍看 `/tmp/chaofu-orch/{A,B}-stdout.log`。

## 2026-10-17 07:02 升级：删对白后静默镜

BAD_extra 主因不是金额念法，而是**对白后的中文静默 ▲**仍在动口（甚至「正要开口」），Whisper 把口型噪声听成英文乱码。

编排新增 `drop_post_dialogue_shots`：BAD_extra 时删掉最后一句对白之后的所有 ▲，并加「片尾硬锁」。
已对 EP20-U05 / EP23-U05 生效，双线已中断旧 attempt、用新提示词重开。

## 2026-10-17 07:14 门禁：对白齐后忽略尾段 ASR 幻觉

删静默镜后仍 overlap=1.0 + BAD_extra：对白已齐，尾段是 Whisper 把呼吸/口型听成英文乱码。

`score_transcript`：一旦前缀片段已盖住全部期望台词，**不再计其后片段为 extras**。同段粘连的真加戏（Roger Tardy）仍 FAIL。Whisper `condition_on_previous_text=False`。对白镜加「说完立即闭嘴定格」。

## 2026-10-18：第二类烧卡 — `BAD_missing` 极短招呼

### 现象

`EP45-U01` 一夜多轮 FAIL（FAIL_ROUND 1→6+，单 unit 门禁失败十余次）：
`missing=['Sienna.']`，`overlap≈0.67`（后半句 `Uncle Victor.` 已齐）。

### 根因

1. **单音节/单词招呼**（`Sienna.`）H3 常缩成气音或口型无声，Whisper 听不到 → 稳定 `BAD_missing`。
2. 编排对 missing 主要做 `strengthen` / 白名单，**没改台词本身** → 同一根因无限 FAIL_ROUND。
3. Fail-fast 只限制「同一次 runner 内 attempt=3」，**编排层 FAIL_ROUND 没有硬顶**，同单元可连烧整晚。

与 `BAD_extra`（对白后乱念）是两类问题；静音锁/删尾镜对 missing **无效**。

### 规避（补丁）

| 规则 | 做法 |
|------|------|
| 拆包/硬化 | 极短招呼写成可听清的短句：`Sienna.` → `Hey, Sienna.`（仍保留原名） |
| FAIL 分类 | `BAD_missing` 且 missing 全是 ≤2 token 专名 → **立刻改写括号台词加音节**，不要只 strengthen |
| 编排硬顶 | 同一 `ep-unit` 连续 FAIL_ROUND ≥3 且 reason 不变 → 必须换接线再抽，禁止空转 strengthen |
| 监控 | followup 看到同一 missing 列表重复 ≥2 轮 → 人工/自动改 `prompt_source`，不要等 |

### 与第一类对照

| | BAD_extra（EP20/23-U05） | BAD_missing 短招呼（EP45-U01） |
|--|-------------------------|--------------------------------|
| overlap | 常 0.9–1.0 | 常 0.5–0.7 |
| 对白 | 已说对 | 有一句根本没出声 |
| 改法 | 删尾镜 / 静音 / 门禁忽略尾段幻觉 | **加长括号内英文** |
| strengthen alone | 不够 | 不够 |

## 总规则（以后双线默认）

1. runner retries≤2；编排对**同一失败指纹**最多 2 轮空 strengthen，第 3 轮必须改台词结构。
2. FAIL 分类下药：extra→静音/删镜；金额→数字化；短 missing→加长招呼。
3. stuck-watch + followup：假死、隧道断、同 missing 连环要报警并停烧。
4. vm106 跳板挂了先修隧道，勿在 ConnectError 上空等烧时间。

## 2026-10-18 生产口径（现行）

潮缚双线复盘后约定（写入 `.cursor/rules/h3-queue-run.mdc` / `h3-render-mode-gate.mdc` / `h3-pack-prep.mdc`）：

1. **默认不开** `--dialogue-gate` / `H3_DIALOGUE_GATE`。先看成片效果。
2. 成片进飞牛后，**每集抽 1～2 个 U** 人工复审（金额、短招呼、对白后还有戏、链头/链尾优先）。
3. 只有用户明确要求，或抽检确认对白问题后再对该批/该类开闸；不要默认全量门禁或全量复审。
4. 若再开门禁：仍须 FAIL 硬顶与按 plan 的 stuck-watch，避免空转烧卡（上文烧卡条款仍有效）。
