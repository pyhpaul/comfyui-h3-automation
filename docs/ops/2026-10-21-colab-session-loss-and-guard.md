# Colab 会话丢失与孤儿机防护（2026-10-21）

## 事故记录

一天内两台 G4（8.9 CU/h）以同一方式丢失：

1. `h3-wenxi-20261021-134358`：宿主进程在首件后退出（只打了
   `COLAB_SESSION_KEPT`，全量从未发出）。会话在无人 exec 后约 20 分钟被回收，
   多烧约 3 CU；本地只剩一个对着空会话计时的看门狗进程。
2. `h3-wenxi-20261021-144455`：生产期每约 4 分钟一次 `colab exec`，39/39 正常
   完成。最后一个 exec 结束（17:09 UTC）后约 3 分钟，再连得到 404/401，
   CLI 判定会话“lost”并清空 `~/.config/colab-cli/sessions.json`；此后所有按名字
   的命令（含 `colab stop`）都返回 not found，但账户侧 assignment 继续计费
   约 75 分钟（约 3 CU），最后用 `scripts/ops/colab_unassign.py` 直接调
   `Client.unassign(endpoint)` 才停掉（已验证 Active=0、rate=0）。

生产成果两次都没丢：产物逐条经 Drive 回执归档到飞牛，本地只负责监控。

## 根因

- Colab 运行时靠客户端连接保活；CLI 的 keep-alive 是宿主进程的子进程，
  宿主退出即失去保活，无人 exec 后数分钟到数十分钟被 Google 回收（时间线吻合，
  宽限时长 Google 不给回执，此点为推断）。
- CLI 的会话名册只是本地 JSON，一次 404/401 就被清掉；账户侧 assignment 是
  另一套状态。名册丢失后，计费与可控性脱节，产生停不掉的孤儿机。
- 我们的编排把生命周期拆给多个短命宿主进程（start-first / run-rest / 后续
  修复各一个），靠“会话应该还在”衔接；生产期密集 exec 意外充当心跳，
  活干完就断。这也是第一台只跑首件的直接原因。

## 现行口径（后续 Colab 生产必须遵守）

1. **单一监督进程**：建会话 → 装环境 → 全部生产 → 验收 → 停机，在同一个
   长命进程内完成，中途不退出；每 2~3 分钟一次轻量 exec 心跳由它兼任。
2. **任务队列放 Drive，VM 自主领活**：远端循环读 Drive 任务清单、写回执；
   本地只监控与归档。本地进程死掉不影响 VM 生产与产物。
3. **干完即停**：不留“待命”会话。修复/后续渲染并进同一次监督运行，
   或另开新会话。
4. **孤儿机兜底**：任何 Colab 生产必须同时挂
   `scripts/ops/colab_orphan_guard.sh`（盯账户级 `colab usage` + 生产心跳文件）。
   它不依赖会话名册：心跳过期先打 `COLAB_ORPHAN_ALERT`，`AUTO_UNASSIGN=1`
   时过期超过硬线自动调用 `scripts/ops/colab_unassign.py` 从服务端停机。
   生产宿主必须至少每条产物 touch 一次心跳文件。
5. **名册丢失先分清两种操作**：停机是账户级操作（OAuth + endpoint 即可，
   `Client.unassign`）；进 VM 干活是运行时级操作，需要每台机的
   runtime proxy token（`SessionState.token`，会过期）。名册被清后，
   `list_assignments` 仍能从服务端拿到该机的现行 `runtimeProxyInfo`
   （新 token + url），理论上可手工重建 `SessionState` 接管——但 CLI 没有
   adopt 命令，这属于无文档的状态手术，且 token 新鲜不证明 VM 本体
   （文件系统/Comfy）还活着。处置顺序：还有活要干且 assignment 刚丢不久，
   可先试重建接管（限时，失败即放弃）；只剩停机目标时直接按 6 走，
   不要在计费状态下做接管实验。
6. **名册丢失的停机路径**：`colab stop` 报 not found 但 `colab usage` 仍
   active≥1 时，不要等网页端——用 colab-cli 的解释器跑
   `scripts/ops/colab_unassign.py --execute`（服务端 `unassign`，已实测有效），
   然后以 `colab usage` 的 Active=0、rate=0 为准确认计费停止。
7. 阶段交接前先验会话存活（ping exec + `colab usage`），发现丢失立刻按 5、6
   处理并报告，不要对不存在的会话继续发命令。

## 接管实测（2026-10-22，结论：第 5 条理论路径成立）

用最便宜的 CPU 会话（0.08 CU/h）实测了一遍：备份名册 → 移走
`sessions.json` 模拟丢失 → 服务端现拿 `runtimeProxyInfo` 重建
`SessionState` → exec、stop。全程无报错，未用到 unassign 兜底：

- 服务端返回的是**新 token**（指纹与旧的不同、长度 222、
  `token_expires_in=3600`），URL 不变——接管必须现调
  `list_assignments`，拿旧 token 拼不回去。
- 重建后 exec 的 hostname 与丢失前一致，是同一台 VM；从丢失到
  重建完成约 5 秒。拖久了 VM 可能已被回收，SOP 仍按限时处理、
  失败即 unassign，不把本次结论外推到「丢很久还能接回」。
- 本次 `kernel_id`/`session_id` 用的是备份值；真实事故无备份时
  只能填 `None`（同 VM 新 kernel，文件在、内存状态丢），该分支
  未单独实测。
- 重建工具已固化为 `scripts/ops/colab_takeover_rebuild.py`
  （支持 `--backup` / `--endpoint` / 唯一 assignment 三种匹配，
  只打印 token 指纹）。全程挂 orphan guard，结束三次复查
  Active=0、rate=0，余额 956.91 不变（实验消耗约 0.001 CU）。
  完整实录：`docs/ops/2026-10-22-colab-takeover-test.md`（本地账本 `runs/colab_takeover_test_20261022.md` 同源）。

## 本批账（潮缚 fx21）

- 会话 `h3-wenxi-20261021-144455`：39/39 完成，GPU 纯渲染合计 125.5 分钟
  （平均 193s/条）；CU 979.82 → 956.91，共 22.91 CU（含孤儿期约 3 CU）；
  另老会话 `...-134358` 用 4.47 CU。
- 产物与对白审核六件套已全部在飞牛
  `archive/潮缚ep01-05 V3版（10.21）/`，问题条清单见
  `runs/chaofu_fx21_problem_units.md`（本地账本）。
