# L0 — 剧本同镜风险解析

## 升 HIGH（剧本路径）

```text
len(on_screen) >= 2 AND has_dialogue
```

标签：`HIGH_RISK_CHORUS`。有「不动唇 / 只有 X 入画」等只加 `lips_lock_hint=true`，**仍升 HIGH**（锁了也要验）。

## has_dialogue / speaker

- `has_dialogue`：段内非空全角 `（…）`，或含「口型同步开口」
- `speaker`：口型句归属——机位括号仅一人则取之；否则口型前最近完整人名；可参考「X说完」

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

## 人工 / 媒体升层

L0 未命中的 U，若审片或抽查见多人同框对白，可写入工单 `promoted_high`，来源 `human` / `media`，附时码或帧路径。  
**低风险只表示不默认强制 L2。**

## 命中理由字段（每镜）

`reasons[]` 例：`bracket:Wade Mercer`、`two-shot-phrase`、`over-shoulder`、`medium:body-mention:Cole`、`land-on-face:Cole`。禁止空理由的 HIGH。
