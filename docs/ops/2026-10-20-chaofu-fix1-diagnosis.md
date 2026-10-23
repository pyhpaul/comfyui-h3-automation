# 潮缚修复一轮（fix1）诊断与方案（2026-10-20）

问题来源：飞牛 `H3_comfyUI_5090/archive/潮缚（10.16）` 里质检改名的目录标注
（比用户转述更具体），逐条核实如下。

## 检测结论

拉取 13 条成片做 ASR 对词 + 抽帧（`scripts/ops/chaofu_dialogue_check.py`，
报告 `.cache/chaofu_check/dialogue_report.json`）：

- **11 条对白条台词内容全对**（ASR 重合度 ≥0.92）。「人物对白不一致」是
  **谁入画/谁动唇**的问题：EP06-U04、EP53-U05 第一镜都是错的人在说
  （Cole/Victor 的台词压在 Wade 脸上）。提示词本身每镜单人近景、说话人
  明确，属渲染端身份绑定失败。
- EP50-U02、EP42-U04、EP51-U06、EP41-U05 另有短语重复（ASR 听出整句或
  半句说了两遍）。
- **EP24 整集**：EP23-U04 为傍晚（图 S01/词/成片一致，合格）；EP24 词与
  图（S02，同一门廊黑夜版）都是黑夜，但成片漂成黄昏光。按「逐条核」
  规则图不换，属光感漂移，加深夜硬锁修。U01/U02 另叠加对白问题。
- EP62（7 条）、EP63（6 条）：无标注，整集重新出。

## 修复动作（用原资产，只加锁）

`scripts/make_chaofu_fix1_jobs.py` 生成 `-fix1` 副本（原 job 不动），
改动只有加锁：

1. 每个对白镜加「本镜画面中只有<说话人>入画，其他人物不入画」；
2. 无对白近景加「<人物>嘴唇合上、全程不动唇、不发声」（已有的不重复）；
3. 全部对白条加「每句台词只说一遍，不得重复或回读」；
4. EP06-U04/EP53-U05 第一镜加服装身份锚（防画错脸）；
5. EP24 六条加深夜硬锁（天空海面全黑、无黄昏余光、唯一光源门廊灯）。

17 个 fix job 全部通过 `audit_pack_prompts.py`（exit 0）。

## 双跑对比（用户决定）

30 条修复全部双跑：A 原工作流（`yz_h3_ep_unit`）+ B 文戏链
（wenwu wenxi variant，武戏 LoRA 关断、**种子随机**并记入 run_meta）。
两版都上飞牛批次 `潮缚修复（10.20）`；B 版放 `<U>-WENXI` 目录、
文件名带 `-wenxi`，与 A 版不打架。

- A 侧：`run_ep_units_profiled.py --continuity motion_latent`，单条重渲
  只渲问题条（下游不动，用户已确认）；父 latent 从飞牛旧批次取最新版
  staged 到 GPU `h3_context/`（`scripts/ops/stage_chaofu_parents.py`）。
- B 侧：`scripts/run_chaofu_wenxi.py`。文武模板原图没有父 latent 入口，
  嫁接 ep_unit 同款三节点（LoadLatent 9101 → MotionContext 9102 →
  Trim 9103）喂 SelfLift 的 positive；分辨率对齐 768×1376 与父 latent
  一致。整集链内自动用上一条 B 版 latent 接力。
- 总控：`scripts/ops/run_chaofu_fix1_all.sh`（串行、失败续跑、逐项日志）。

## 已知风险

- B 侧嫁接 + SelfLift 首次组合：试点 EP23-U05 首跑在 SelfLift 阶段
  CUDA 异步释放崩溃（`cuMemFreeAsync INVALID_VALUE`，Comfy 进程退出），
  重启后重试点验证。若复现，B 侧改独立渲染（不接父 latent）再议。
- 单条重渲与下游旧条接缝：首秒由新 latent 重生成，下游头部不重渲，
  接缝可能有细微跳变（用户已知并接受）。

## 最终结果（2026-10-21）

13 个问题单元 × 双链（原工作流 A 侧 + 文戏 B 侧）共 26 份全部定版，
逐条帧审通过（放宽标准见
`docs/ops/2026-10-21-chaofu-fix-retrospective-and-standard.md`），
归档于飞牛 `H3_comfyUI_5090/archive/潮缚修复定版（10.20）/`
（分 `原工作流/`、`文戏工作流/`，根目录 `00-修复清单.md`）。

- 严格通过 11 份；放宽通过（附 EDIT_NOTE 剪辑点）15 份
  （文戏 7、原工作流 8）。
- 原工作流最后 9 条的收口：5 条从门禁遗留候选救回（EP51-U06、
  EP33-U01、EP23-U05、EP24-U01、EP24-U02，latent 经 /history 回收），
  4 条新种子（--seed-offset）重渲解决（EP06-U04、EP23-U01、
  EP41-U05、EP53-U05，后两条中的 EP23/EP41 为放宽通过）。
- 未纳入本轮：EP24-U03~U06、EP62（7 条）、EP63（6 条）全量重渲。
- EP24 夜景：定版为真夜（深蓝夜空 + 门廊灯），与参考图一致。
