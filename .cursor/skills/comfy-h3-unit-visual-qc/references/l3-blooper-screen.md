# L3 — 穿帮初筛（triage）

目标：**减低人工扫穿帮的成本**。模型先给风险档，人优先看 HIGH；漏几条可接受，假阳性可接受，只要比全量人扫省时间。

不是对白/口型层（那是 L1/L2）。不是定案级 FAIL，也不是「空嫌疑 = 已清场」。

## 何时跑

- 默认 **`NOT_RUN`**（sidecar 不加 `--l3`）。
- 开跑时机：赢家/定版前，或人觉得「这批看起来一堆乱套」时批量初筛。
- 不要每条种子都跟；脚本：`scripts/ops/pilot_l3_blooper_screen.py`。

## 状态接口（plan/report）

| 状态 | 含义 |
|---|---|
| `NOT_RUN` | 默认；穿帮未检查 |
| `SUSPECTS_OPEN` | 有嫌疑清单（看 `triage_risk`） |
| `SCREENED_NO_SUSPECTS` | 模型未列嫌疑；**仍非人工清场** |
| `TRIAGE_PARTIAL` | 有可用答案，但结构字段有瑕疵；仍可按 `triage_risk` 排队 |
| `SCREEN_INCOMPLETE` | 模型无答案 / CLI 失败 |
| `CLEARED_BY_HUMAN` | 仅人工关闭后使用 |

另写 **`triage_risk`**：`HIGH` | `MED` | `LOW` | `NONE`。

| triage | 人侧动作 |
|---|---|
| HIGH | 先看（多肢/身份熔/道具乱/≥3 嫌疑） |
| MED | 有空再看 |
| LOW / NONE | 可跳过细扫；抽检仍可 |

## 原则（初筛口径）

- 盯**大体量视觉乱套**：多肢、手熔、身份串、道具变形、构图裂、画外入画。
- **frame_id 只作导航**：未知/自创 id（如 `ov:`）降级为 `soft_nav_hints`，**不**整单 `SCREEN_INCOMPLETE`。
- 密窗帧前缀 `D###`，总览 `F###`；提示模型禁止 invent 标签。
- 自动只出嫌疑 + 风险档；确认缺陷后再开复修。不自动重渲。
- 未执行时写明「穿帮未检查」。

## 双通道（仍适用）

用户要求 L3 时，局部形体 + 连续性/剧本约束都要扫；缩略拼图不能支撑「细指节已排除」。
假阳性提示见脚本 `FALSE_POSITIVE_HINT`（悬空白纸、地球仪≠钟、运动模糊、正常双手重叠）。

## 嫌疑类

`extra_limb` | `anatomy` | `extra_prop` | `identity_melt` | `wardrobe_continuity` |
`prop_continuity` | `composition_constraint` | `other`
