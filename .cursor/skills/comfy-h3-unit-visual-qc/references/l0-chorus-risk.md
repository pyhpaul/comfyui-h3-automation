# L0 — 剧本同镜风险解析

## 升 HIGH（剧本路径）

```text
len(on_screen) >= 2 AND has_dialogue
```

标签：`HIGH_RISK_CHORUS`。有「不动唇 / 只有 X 入画」等只加 `lips_lock_hint=true`，**仍升 HIGH**（锁了也要验）。

## has_dialogue / speaker

- `has_dialogue`：提取非空台词或明确发声动作，排除资产 ID、普通说明括号、无声张嘴。
  「口型同步开口」但缺台词时仍保留风险工单，另标 `MISSING_EXPECTED_TEXT`。
- `speaker`：取「X … 口型同步开口/说/问」发声分句的语义主语；
  用该句上下文与「X说完」交叉核对。机位人物只作佐证，不覆盖明确发声主语。
- 不采用人物表首名、最后出现的人名或机位第一个名字兜底。例：
  「Ethan视线钉在Noah脸上，口型同步开口」的说话人是 Ethan，不是 Noah；
  「越过Ava拍Ethan，Ethan…说」也不是 Ava。
- 每个台词块保留 `dialogue_id`、原文跨度、`expected_speaker`、`voice_kind`
  （`lip` / `inner_os` / `phone_os` / `offscreen` / `unknown`）与 `speaker_evidence`。
  `speaker` 可作旧字段别名；同镜多句/多说话人应分别列出，不用单值覆盖全部台词。
- 身份或分句归属冲突时写 `UNKNOWN` + `REVIEW_PARSE`，不因解析失败降风险。
  电话声、内心 OS 不自动要求对应真人入画；听者张嘴与否留到 L2 核实。

资产码式括号（如纯 ID）不当台词。

## on_screen：Strict vs Medium

对每个 `▲` 段独立算。P1–P2 **双跑**，结果分列。

### Strict

计入：

- 机位括号 `［…］` 内点到的剧名人名
- 明确同框：「A 与 B」「A、B 面对面」「双人中景」等

不计入：

- 「A 望向 B / 看着 B / 目光落到 B」——**不证明 B 入画**
- 仅被提及的画外对象

「镜头落到 B 脸上 / 近景［B正面］」：

- B ∈ on_screen
- **不要**因此自动保留上一镜的 A；A 是否同框看**本段**括号与同框措辞（过肩「越过 A 拍 B」→ A 与 B 可同时在）

### Medium

Strict 全部 +：本段正文出现、且未标「画外」「不入画」「其他人物不入画」的剧名人名。

仍排除纯「望向 B」把 B 拉进 on_screen 的路径（与 Strict 相同：望向 ≠ 入画）。「落到 B 脸上」已由镜头描述覆盖。

引号里的名字、对白点名、电话联系人、屏幕肖像不直接算真人入画。
每条新增人物须关联本镜的具体语句；禁止跨句匹配「同框」后把远处视线目标拉入 Strict。

### Loose

仅校准基线：U 级 `人物：` 全员。不作正式命中。

## 切镜与过肩

| 写法 | 倾向 |
|---|---|
| 正反打拆成两段 ▲，每段括号一人 | 各段 on_screen 常为 1 → 不升 HIGH |
| 过肩：越过 A 拍 B | A、B 常同属 on_screen |
| 中景［A 与 B］ | 两人 |
| 固定镜头空镜/道具 | 无人名 → 无对白则无关 |

## 灰区 REVIEW_PARSE

正文出现另一人名，但未进入当前模式的 on_screen，且存在歧义（纵深、反应、望向）。

- 不自动升 HIGH
- **必须复核**
- 可升层条件：确认多人同框；或实际媒体多出人物；或已知坏例 → 升 HIGH 并写 `promote_reason`
- 灰区未处理完 → 不得宣布同镜排查完整

灰区统计单位统一为一个 `gray_id`（镜号 + 歧义语句跨度 + 原因）；同一歧义可关联多人。
报告同时给未关闭工单数与关联人物数。跨 agent 先按原文跨度对齐，不能仅拿灰区总数比较漏报。

## 双跑校验

- 逐镜保留人物与说话人，不能仅凭 HIGH U 总数相等判断解析正确。
- 同一规则下 Strict 人物应是 Medium 子集；多出的 HIGH 镜须解释具体新增人物。
- `UNKNOWN`、画外音、无声反应镜单列检查。没有证据时不能用前后镜继承人物。
- 校准例：EP01-U01 ▲2 Ethan、▲3 Sienna；EP01-U02 ▲1 Noah、▲2 Ethan、▲3 Damian。
  这些用于检查主语解析，不是硬编码整批人名的替代算法。

## 人工 / 媒体升层

L0 未命中的 U，若审片或抽查见多人同框对白，可写入工单 `promoted_high`，来源 `human` / `media`，附时码或帧路径。  
**低风险只表示不默认强制 L2。**

## 命中理由字段（每镜）

`reasons[]` 例：`bracket:Wade Mercer`、`two-shot-phrase`、`over-shoulder`、`medium:body-mention:Cole`、`land-on-face:Cole`。禁止空理由的 HIGH。
