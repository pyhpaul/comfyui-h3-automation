# L3 — 穿帮筛查（占位）

## 状态接口（必填于 plan/report）

| 状态 | 含义 |
|---|---|
| `NOT_RUN` | 默认；未做穿帮检查 |
| `RUNNING` | 抽帧/模型进行中 |
| `SUSPECTS_OPEN` | 有未确认嫌疑 |
| `CLEARED_BY_HUMAN` | 嫌疑已人工关闭或确认无穿帮 |

P1–P3 默认 **`NOT_RUN`**。不引入强制每秒抽帧全量流程。

## 原则（将来试点）

- 自动只出 `SUSPECT` + 时码 + 帧路径；人确认后才进缺陷单。
- 不定案、不自动重渲。
- 未执行时文案只能是「穿帮未检查」，禁止「视觉全面通过」。

## 嫌疑类（预留）

`extra_limb` | `anatomy` | `extra_prop` | `identity_melt` | `other`
