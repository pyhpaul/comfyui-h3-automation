# 报告模板

## plan.md 顶栏（P1 固定）

```markdown
# Visual QC Plan — <batch> / <EP>

- **状态：风险排查完成、说话人未定案**
- 规则版本：comfy-h3-unit-visual-qc / design 2026-10-23
- 解析：Strict + Medium 双跑（P2 前用于校准；最终成片仍人审）
- L1：<NOT_RUN|path>
- L2：NOT_STARTED
- L3：NOT_RUN（穿帮未检查）
- 灰区：<n> 条待复核；未复核则同镜排查不完整
```

## plan.json 最小字段

```json
{
  "schema": "visual_qc_plan_v1",
  "banner": "风险排查完成、说话人未定案",
  "batch": "",
  "episode": "",
  "rule_version": "comfy-h3-unit-visual-qc@2026-10-23",
  "layers": {
    "L0": "DONE_DUAL_MODE",
    "L1": "NOT_RUN",
    "L2": "NOT_STARTED",
    "L3": "NOT_RUN"
  },
  "units": [
    {
      "unit": "U01",
      "media_sha256": "",
      "media_status": "present|absent",
      "prompt_path": "",
      "prompt_sha256": "",
      "strict": {"unit_risk": "HIGH_RISK_CHORUS|LOW", "high_shots": [], "shots": []},
      "medium": {"unit_risk": "HIGH_RISK_CHORUS|LOW", "high_shots": [], "shots": []},
      "review_parse": [],
      "promoted_high": []
    }
  ],
  "summary": {
    "units_total": 0,
    "strict_high_units": 0,
    "medium_high_units": 0,
    "gray_open": 0
  }
}
```

每镜 `shots[]` 建议：`shot`, `on_screen`, `has_dialogue`, `speaker`, `risk`, `reasons[]`, `excerpt`。

## report.md（P3+）

在 plan 之上增加逐 U 的 L2 逐句结论与 `defect_class`；L3 非 `NOT_RUN` 时列嫌疑结案。  
无完整实看不得写通过。
