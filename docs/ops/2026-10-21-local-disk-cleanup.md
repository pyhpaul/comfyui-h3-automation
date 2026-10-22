# 本地磁盘清理记录（2026-10-21）

**结论：** 本地不留历史副本。原包在飞牛 inbox、成片在飞牛 archive，随时可按集
重拆。规矩已固化为项目规则 `.cursor/rules/h3-local-disk-cleanup.mdc`。

## 执行前的问题

- `jobs/ep_units/` 累积 15G（每条 job 复制一套参考图，约 15MB/条）；
  `outputs/` 累积 12G（1439 个 prompt 输出目录未按「上传后删除」执行）；
  `.cache/` 约 5.9G（fix1 验证产物、A/B 侧测、抽查拉回的 mp4 副本等）。
- 典型教训：新剧全剧包（EP01–EP71，854MB）在 `/tmp`/`.cache` 下载+全量
  解压+全量建 job，光中转就约 1.8G、job 约 6G 起，而实际只跑其中几集。

## 两轮清理（共约 32G，磁盘占用 219G → 187G）

第一轮（分级保留）：

- `jobs/ep_units` 15G → 4.3G：删 1209 个 10 天前的历史 job
  （屠龙、奶茶、测试-v7、死人回来了、旧 H3-manual 各版本等，11.45G）。
- `outputs` 12G → 1.2G：删 1328 个 2 天前的输出目录（10.64G）。
- `.cache` 约 5.9G → 67M：删 fix1 验证 3.9G、侧测/测试包、v2 对白抽查
  mp4 副本、离婚包残缺下载；方位 A/B 成片抽帧已镜像飞牛并验完，
  本地只留脚本/日志/提示词文本。

第二轮（用户确认潮缚线与 10 天内的一并清）：

- `jobs/ep_units` 与 `outputs` **全部清空**（再清 5.5G）。删前已确认本地
  无 runner 进程在读 job（v3 处于暂停、两隧道队列无本地驱动）。

## 第三轮（2026-10-22，说话人锁定测试收尾，共约 12G）

- `.cache/chaofu_probe`（475M）、`.cache/chaofu_fx21_check`（1.1G）、
  `.cache/chaofu_fx21_colab`（1.9G）：串嘴调查与探针的过程产物，
  候选与结论已在飞牛待审区、总记录已归档，整目录删。
- `jobs/` 全部清空（5.8G → 4K）：518 个单元 job（继母 406、寿命掮客 54、
  潮缚 fx21 39、潮缚 v2 19）与 wenwu/facerefine 测试工作区。用户确认
  继母、寿命掮客后续都重拆重做，本地 job 无保留价值。
- `.cache/` 其余全部清空（3.0G → 4K）：`wenxi_models`（2.0G，模型真本在
  Drive 模型树）、`chaofu_fix1_verify`（634M，成片在飞牛 archive）、
  `colab_wenxi_setup`（289M）、`orientation_ab`（67M，10-21 保留的它，
  其脚本集已回收进 `scripts/ops/`，本轮清）、`chaofu_redo_packs`（41M）。
- 规则已补两条：模型暂存、Colab 会话工作目录明确按任务级缓存清
  （见 `.cursor/rules/h3-local-disk-cleanup.mdc`）。
- 结果：仓库共 1.8G（`.worktrees` 的 venv 1.7G + `runs/` 88M），
  磁盘 111G/1007G。

## 保留物

- `runs/`（86M）：运行日志、审核 JSON、对白报告等账本。
- `.cache/orientation_ab`（67M）：Colab 文戏配置子任务进行中仍在引用
  其脚本集，该子任务收尾后清。
- 飞牛侧：inbox 各原包（含潮缚 v1/v2/v3、方位 A/B 镜像、
  EP01-V2 对白审核）与 archive 全部成片未动。

## 今后口径（已入规则）

1. zip 只中转：jobs 建好审核过，立刻删 zip + 解压目录。
2. 成片四件套确认进飞牛后，删该批 jobs 与 outputs；要修按集重拆。
3. 任务缓存收尾即清；大证据先镜像飞牛验完再删本地。
4. 删前查 runner 进程与队列，别误伤其他会话在跑的批次。
