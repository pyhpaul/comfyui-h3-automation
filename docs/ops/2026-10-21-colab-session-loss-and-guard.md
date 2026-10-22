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

1. **单一监督进程 + 独立保活进程**：建会话 → 装环境 → 全部生产 → 验收 →
   停机仍由同一个长命监督进程负责；但每 2 分钟一次轻量 exec 保活必须由
   独立进程组中的 keeper 承担，不能由监督进程兼任。监督进程崩溃、退出或
   卡死时，keeper 仍须继续连接 VM，直到收到显式 stop flag 或服务端确认
   assignment 已消失。
2. **VM 侧批量自主渲染 + Drive 回执续跑**：任务清单随输入包上传，VM 侧
   batch 逐条渲染并在进入下一条前把成品与 `phase.json` 回执发布到 Drive；
   本地只轮询回执归档。新 VM 必须按旧 Drive remote 的 success 回执跳过
   已完成单元，不能只信本地 phase 文件。监督进程死掉不应丢已发布产物，
   但 VM 本体仍只能靠独立 keeper 保活。
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

## 二次事故与保活结论（2026-10-22，离婚后 v23）

同一死法在离婚后 EP01–EP10 生产中再次出现，时间线把机制钉死了：

- 09:45 UTC 建会话 `h3-lihun-20261022-094504`，环境与文戏安装完成。
- 09:54 原宿主被人为停掉后，只剩本地心跳文件写入进程与 orphan guard；
  09:58 领养宿主接上，两批共 50 条。
- 10:04 领养宿主因第二批 mover 的 exec 排在忙碌内核后 180 秒超时而崩溃
  （当时 `exec_retry` 不重试 `TimeoutError`）。它退出前打印的
  `SESSION_KEPT` 只证明那一刻 assignment 还 active，不代表之后有人保活。
- 宿主死后 guest 仍在 VM 内核里继续渲染并向 Drive 发回执：EP02-U01
  10:12、U03 10:18、U04 10:21 先后落地。这证明已发出的内核执行在客户端
  断开后还能续跑一阵，但 Drive 写入不是 Google 运行时管理器的保活活动。
- 约 10:22 VM 被回收；10:23:26 orphan guard 看到 Active=0 后退出。
  此时 `sessions.json` 已是 `{}`，本地没有任何活着的 Colab
  keep-alive/exec 进程。余额停在 951.81，Active=0、rate=0。
- 抢救结果：EP01-U01～U04、EP02-U01～U04 共 8 条已从 Drive 归档飞牛
  `archive/离婚后（10.22）/`，逐条对白 QC 均 PASS；只丢当时在途的一条。

为什么“有心跳/有 guard”仍保不住：

- 本地心跳文件只给本地 orphan guard 看，Google 看不见；guard 与付费
  watchdog 都只轮询计费/执行停机，物理上不能给 VM 续租。
- Colab 的有效保活是“本地仍有活着的 CLI 进程连着该 runtime”。fx21
  生产那台能活完全程，是每约 4 分钟一次 exec 无意中充当了心跳。
- 一条挂几十个单元的长 exec 也不是可靠 lifeline：它会提前返回、超时，
  或客户端进程先死；服务端内核虽继续跑，但最后一个本地连接消失后，
  约 15–20 分钟宽限结束 VM 就被回收。
- 所以监督进程是生命周期单点时，保活不能再与它共生死；
  `SESSION_KEPT` 更不能当作“之后会一直活着”的证据。

已固化的根治实现（2026-10-22）：

1. `scripts/ops/colab_heartbeat_keeper.sh` +
   `scripts/ops/colab_keepalive_probe.py`：宿主建会话后立即以独立进程组
   启动 keeper，每 120 秒一次轻量 exec；只在显式 stop file 出现或
   `colab usage` 确认 Active=0 时退出。probe 排在忙碌内核后面超过
   CLI 自身 timeout 不算会话丢失，只要 assignment 仍 active 就继续
   重试，并以本地 `timeout 150` 给每次尝试加硬上限、尝试开始即写日志。
   验收看
   `runs/colab_heartbeat_keeper.log` 的新鲜 `keeper: ok` 时间戳，
   不能只看 Active=1。
2. `scripts/ops/colab_h3_wenxi_batch_phase.py`：guest 逐条发布 Drive
   回执；新 VM 通过 `H3_DONE_REMOTES` 查旧 session remote 的 success
   回执，已完成单元只向新 remote 发 `skipped_done_remote` 标记，
   不重渲、不重复拉文件。
3. `scripts/ops/colab_h3_lihun_batch_host.py`：宿主负责启动 keeper；
   mover/stage 的 `TimeoutError` 纳入重试；batch exec 提前结束或抛错
   不再让监督直接退出，而是等 Drive 终态回执、缺哪条就重发 guest
   （guest 按回执跳过已完成）。正常停机时先写 keeper stop file，
   `--no-stop` 时 keeper 与 guard 继续独立存活。orphan guard 的
   heartbeat 改盯 keeper 的真实日志：监督死、keeper 活属于可恢复状态，
   不误杀；keeper 死后日志变陈旧，guard 才按硬线服务端停机。禁止再用
   无条件 touch 本地文件的循环给 guard 喂心跳，那会把断路器短路。
4. 停机权集中：只有全部完成后的显式停机路径能写 `KEEPER_STOP` 并
   `colab stop`；orphan guard 继续只做计费兜底，不承担保活。

名册反复丢失的根因（同日下午在同一会话上又丢两次后定位）：runtime
proxy token 只有 3600 秒寿命，CLI 的 keep-alive 守护只 ping 账户端点、
不刷新 `sessions.json` 里的 token；token 过期后下一次按名 exec 撞
404/401，CLI 即判定会话丢失并清空名册（CLI 日志里 kernel 404 的时间
与建会话/接管后约 1 小时精确吻合）。assignment 与 VM 本体此时都还
活着，所以接管重建每次都能成功。

5. `scripts/ops/colab_session_guardian.sh`：token 轮换守护。每 40 分钟
   主动调 `colab_takeover_rebuild.py` 换新 token 重写名册（过期前
   轮换，不等撞墙），名册已丢时 60 秒内自动重建；每次轮换重生 CLI
   keep-alive 守护并杀掉旧的。备份只存 endpoint/kernel/session
   （不含 token）。宿主建会话后自动挂 guardian。验收看
   `runs/colab_session_guardian.log` 的 `rebuilt` 记录。

多开实测（2026-10-22）：生产会话运行中另开一台 G4 测试会话，
`colab usage` 显示 Active assignments: 2、rate 17.80/h（两台分别
计费）；测试 VM exec 正常（hostname 不同），生产机渲染/归档不受
影响；`colab stop` 测试会话后回到 Active=1、rate 8.90，名册只剩
生产会话。结论：付费模式支持多台并发，按集拆分并行生产可行，
每台需独立 keeper + guardian + 归档通道（Drive remote 按会话隔离）。

剩余边界：keeper 与 guardian 仍在本地工作站上。若 WSL/工作站休眠、
断网或两者都退出，VM 侧没有已知的自续租通道，仍会在宽限后被回收；
长批次必须同时盯 keeper 与 guardian 日志新鲜度，而不只是盯监督进程。

## 双线衔接卡死（2026-10-22，离婚后 v23）

EP01–EP10 全部落地后约 35 分钟没有双线出片，只有 B 线在产。两层根因：

1. **旧批次 exec 客户端挂死**：A 线最后一批的 guest 其实早已把
   EP06–EP10 全部渲染并发布 Drive 回执、宿主也已逐条归档飞牛，但
   `colab exec` 客户端在等 reply 处挂死 69 分钟不返回。宿主主线程
   卡在 `exec_file` 上不退出，等待宿主退出才喂下一包的 chain 脚本
   就永远等不到触发点；其间 A 机只计费、不产新条。
2. **领养检查与双机并发不兼容**：chain 拉起的新宿主在 adopt 分支
   写死 `active == 1` 才算领养成功；双机同时在线时
   `Active assignments: 2`，检查必然失败，宿主秒退（traceback 后
   仍打印 `SESSION_KEPT`，chain 记到的退出码还是 0，容易误判为
   正常结束）。

处置（已验证有效）：确认该批所有单元回执都已归档后，只
`kill -TERM` 挂死的 exec 客户端——guest 侧工作已完成，杀客户端
不丢任何成片；宿主随即打印 `BATCH_EXEC_ERROR` 并靠
`wait_for_bundle` 以既有回执判定批次完成、正常收尾退出，keeper
与 guardian 不受影响。随后给 adopt 分支加 `--allow-concurrent`
语义（并发时 `active >= 1` 即确认领养），手动以
`--adopt-session … --allow-concurrent --extra-input EP11-15
--extra-input EP16-20` 拉起新宿主，EP11-U01 随后入队，双线恢复。

防复发口径：

- 双机时代的 chain/领养命令**必须带 `--allow-concurrent`**，无论
  是建新会话还是领养旧会话；`runs/` 下的临时 chain 脚本是本地
  账本（gitignore），写新 chain 时照此口径，不要漏旗标。
- 批次全部回执已归档、但宿主超过约 30 分钟仍卡在单个 exec
  客户端不退出时，按上面处置杀客户端让宿主按回执收尾；不要杀
  宿主主进程，更不要停会话（keeper/guardian 还在保活）。

## 本批账（潮缚 fx21）

- 会话 `h3-wenxi-20261021-144455`：39/39 完成，GPU 纯渲染合计 125.5 分钟
  （平均 193s/条）；CU 979.82 → 956.91，共 22.91 CU（含孤儿期约 3 CU）；
  另老会话 `...-134358` 用 4.47 CU。
- 产物与对白审核六件套已全部在飞牛
  `archive/潮缚ep01-05 V3版（10.21）/`，问题条清单见
  `runs/chaofu_fx21_problem_units.md`（本地账本）。
