# Colab 文戏恢复优化待办（2026-10-21）

触发条件：Colab 文戏 smoke 通过（`runs/colab_wenxi_setup.md` 出现
「Colab 文戏可接生产」结论）后、第一批 Colab 生产任务开跑前，立即做
下面的优化，不要等攒到下一次冷启动再吃一遍慢恢复。

## 基线（已实测）

- restore 阶段 727s（第一轮，第二轮同节奏）；清单为 81 条 rclone 命令：
  主 models 树并行 copy（`--transfers 3`）之外，3 个大模型共 76 个分片
  （VAE 6 + text_encoder 30 + diffusion 40）是逐片串行 `copyto`。
- smoke 门到门约 30–35 分钟：分配+preinstall 约 0.5 分钟、restore 约
  12 分钟、setup+SelfLift 安装+重启 约 1 分钟、preflight 约 1 分钟、
  文戏 7 模型单独 copy（2GB）几分钟、渲染 5–10 分钟、抽帧+停会话。
- 计费 8.9 CU/hr，恢复期间全价烧钱。

## 教训（2026-10-21 第二轮 smoke，优化前必改）

第二轮 preflight 全 PASS（宿主核验 19 项）后，smoke 一条都没提交就
死了：共享 `exec_file` 在 phase 启动前用 15 秒超时 `rclone cat`
Drive 上的 preflight 回执算 manifest 哈希，Drive 慢了一下就超时；
宿主 `finally` 又无条件停会话。一台花了 12 分钟恢复的热机毁在一次
15 秒的读回执上，白烧约 1.9 CU，还要再付一轮恢复才能重试。

原则：**热会话里一切瞬时失败（Drive 读、exec 瞬断、回执未落盘）
先在会话内重试，绝不因为宿主侧读回执失败就关机**；关机只留给
preflight 不过、渲染确定性失败、或重试耗尽。已在
`.cache/colab_wenxi_setup/scripts/wenxi_host.py` 落地（回收进
`scripts/ops` 时保留）：

- preflight manifest 哈希由宿主用 120 秒超时+3 次重试的
  `remote_bytes` 预先算好，经 `input_manifest_sha256` 传给
  `exec_file`，绕过其内置 15 秒远程拉取；
- smoke phase 失败或回执缺失时在同一会话内重试 1 次（固定种子，
  重复提交最多多渲一条 smoke，可接受），两次都拿不到回执才报错
  停会话。

## 优化项

1. [x] **7 个文戏模型并进主 models 树**（2026-10-21 完成：无同名冲突、
   server-side copy 合并、主树 10 文件 SHA 全 match、宿主去掉独立 copy
   阶段、preflight 对 restore 后本地树全 match，见
   `runs/colab_wenxi_setup.md` 恢复优化一节）：把 Drive
   `comfyui-h3-colab-dedicated/wenxi-extras/` 的 7 个模型
   （loras×5、latent_upscale_models×1、vae_approx×1，清单与 SHA 见
   `runs/wenxi_models_supply.log` 与 `runs/colab_wenxi_setup.md`）
   按子目录合并进 restore 用的主 models 树
   （`rental-20260924-5090/models/`），让 restore 的 3 路并行 copy
   一并带下来；删掉独立的 `wenxi_models_copy` 阶段。preflight 的
   KNOWN_SHA 改为对主树核验。注意不要覆盖主树里同名不同版的文件，
   合并前逐个比 SHA，同名不同 SHA 先报告再定。
2. [x] **分片下载并行化**（2026-10-21 完成：`--transfers 8` 整目录并行、
   `H3_RESTORE_PART_TRANSFERS=1` 可回退串行、拼接 SHA 与现行一致、
   基线落盘 `runs/colab_wenxi_restore_baseline.json`、restore 727s→292.7s）：
   76 个 model-parts 从逐片串行 `copyto` 改为
   并行拉取（`rclone copy` 带 `--transfers` 或等价并发），拼接后逐个
   验 SHA 与现行一致。串行是 restore 12 分钟的主要构成。
3. （可选，视 1+2 效果）做一份 wenxi-ready 的冻结快照，把
   SelfLift 节点也固化进去，省掉每轮 `wenxi_install` 的装节点+重启；
   做之前先确认快照体积与 Drive 配额。

## 验收

- [x] 优化后完整冷启动一轮：记录 restore 阶段耗时（对比基线 727s）、
  preflight 全 PASS（28 class_type + 全部模型 SHA）、smoke 再出 1 条
  确认无回归，再停会话验零（0 active、0.00/hr）。
  （2026-10-21 会话 `h3-wenxi-20261021-131142`：restore 292.7s、
  preflight 全 PASS 19 项、smoke `fab5644a…` 180.4s 帧检非黑非分屏、
  停会话验零、本轮 1.84 CU，见 `runs/colab_wenxi_setup.md`。）
- [x] 结果追加到 `runs/colab_wenxi_setup.md`，本文件勾掉已完成项。

## 顺带回收

- [x] `.cache/colab_wenxi_setup/scripts/` 的 `wenxi_install.py`、
  `wenxi_preflight.py`、`wenxi_host.py` 按第一轮报告建议回收进
  `scripts/ops/`（`colab_h3_wenxi_*.py`，另含 phase 与无操作版
  models_copy），宿主默认从 `scripts/ops/` 跑；`.cache` 只留运行数据，
  未按 `h3-local-disk-cleanup.mdc` 删除（input/vendor/证据仍在用）。
