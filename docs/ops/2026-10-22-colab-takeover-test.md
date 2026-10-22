# Colab 丢失句柄接管实验 + 《离婚后》文戏环境准备核查（2026-10-22）

## 结论先行

- **接管可行（本次实测成功）**：最小 CPU 会话在模拟丢失本地名册后，用 colab-cli 自带解释器调 `Client.list_assignments()` 拿到同一 endpoint 的现行 `runtimeProxyInfo`，手工重建 `SessionState` 写入 `~/.config/colab-cli/sessions.json`，随后 `colab exec` 在**同一台 VM（hostname 不变）**上成功执行，再用重建的会话正常 `colab stop`。全程未走服务端 unassign 兜底（不需要）。
- **token 确实会轮换**：`list_assignments` 返回的新 token 与原名册 token 指纹不同（见下），URL 不变。所以「拿旧 token 拼回去」不行，必须从服务端现拿；事故文档第 5 条的理论路径成立。
- **无孤儿会话**：结束时及报告落笔前复查 `colab usage` 均为 `Active assignments: 0`、`Usage rate: 0.00/hr`，`colab sessions` 为无活动会话，orphan guard 自行以 `active=0` 退出。
- **CU 账**：开会话前 956.91 CU → 结束后 956.91 CU（余额显示未变）。本次是 CPU 会话，费率 0.08 CU/h、存活约 1 分钟，理论消耗约 0.001 CU，低于余额显示精度。注意余额结算有滞后，最终以 `colab usage` 为准。
- **文戏环境准备有缺口但可补**：脚本与 Drive 模型树齐全，缺的只是本地 `.cache/colab_wenxi_setup/` 运行数据（2026-10-21 磁盘清理时按规则删掉），可从 Drive 定点重拉；真正的生产缺口是 `input/manifest.json` 这类**按单元生成的输入**和只做 SMOKE 的现行宿主，见缺口清单。

## 第一步：接管实验实录

会话：`takeover-20261022-092028`（CPU / DEFAULT / Standard，最便宜形态，无 GPU、无 wenxi 安装、无渲染）。单一监督脚本 `.cache/colab_takeover_test/supervisor.sh` 全程不退出地执行下列步骤，原始日志在 `.cache/colab_takeover_test/steps.log`。

| 时刻 (UTC) | 步骤 | 实际结果 |
|---|---|---|
| 09:20:28 | 开会话前 `colab usage` | balance 956.91，rate 0.00/hr，Active 0 |
| 09:20:30–35 | `colab new --session takeover-20261022-092028`（无 `--gpu/--tpu`） | `Session READY`，rc=0 |
| 09:20:35 | 启动 orphan guard | `HEARTBEAT=.cache/colab_takeover_test/heartbeat AUTO_UNASSIGN=1 POLL_S=30 bash scripts/ops/colab_orphan_guard.sh`（GRACE/HARD 用脚本默认 10/30 分钟）；监督进程每 20s touch 心跳 |
| 09:20:37 | 开会话后 usage | rate **0.08/hr**，Active 1，balance 956.91 |
| 09:20:41 | 基线 exec（探针：打印 hostname） | `TAKEOVER_EXEC_OK hostname=1cd7d86e907d`，rc=0（此步让 CLI 把 kernel_id/session_id 写进名册） |
| 09:21:11 | 备份名册到 `.cache/colab_takeover_test/sessions_backup.json`（0600） | 含 endpoint `m-s-kkb-ass1b2-10c3smrzhounb`、token 指纹 `8ec09fea295e`（长 222）、kernel_id/session_id 均在 |
| 09:21:11–16 | 顺路轻量 Drive preflight（本机 rclone 只读列 Drive 主模型树） | rc=0，10 个直存模型文件在（含已并入的 7 个文戏模型），未装任何环境 |
| 09:21:16 | **模拟丢失**：`mv ~/.config/colab-cli/sessions.json .cache/colab_takeover_test/sessions_lost_simulation.json` | 原路径名册不存在（`exists_now=no`）；此期间未对该会话发任何按名命令（避免 CLI 清册/误判） |
| 09:21:19–21 | **重建**：CLI 解释器跑 `.cache/colab_takeover_test/rebuild.py` | 见下节，`REBUILD_OK`，rc=0 |
| 09:21:21–24 | 用重建会话 exec 同一探针 | `TAKEOVER_EXEC_OK hostname=1cd7d86e907d`（**与丢失前同一主机名**），rc=0 |
| 09:21:24–26 | 用重建会话 `colab stop` | `Session terminated.`，rc=0，未触发 unassign 兜底 |
| 09:21:28–54 | 三次 usage + sessions 复查；guard 退出 | 三次均 Active 0 / rate 0.00；`No active sessions found on server.`；guard 日志 `active=0, guard exit` |

### 重建一步的细节（哪一步通、哪一步报错）

`rebuild.py` 用 `~/.local/share/uv/tools/google-colab-cli/bin/python3` 运行（与 `colab_unassign.py` 同一解释器要求），逻辑：`get_credentials(~/.colab-cli-oauth-config.json, OAUTH2)` → `Client(Prod(), creds).list_assignments()` → 按备份里的 endpoint 唯一定位 → 用返回的 `runtimeProxyInfo` 新建 `SessionState` → `StateStore().add()` 落盘 → `spawn_keep_alive(endpoint, name)` 拉起新 keep-alive 并回写 pid。

实测输出（已脱敏，只留指纹）：

```text
LIST_ASSIGNMENTS count=1
 assignment endpoint=m-s-kkb-ass1b2-10c3smrzhounb accelerator=NONE variant=DEFAULT machine_shape=STANDARD token_expires_in=3600 url_host=8080-m-s-…prod.colab.dev
MATCH_BY_ENDPOINT count=1
TOKEN old_fp=8ec09fea295e new_fp=185d24bdd478 same=False old_len=222 new_len=222
URL same=True orig_kernel_id_present=True orig_session_id_present=True
SESSIONSTATE_WRITTEN
KEEP_ALIVE_SPAWNED pid=756691
REBUILD_OK
```

- 通的：OAuth 凭据、`list_assignments`、按 endpoint 匹配、新 token/URL、`SessionState` 字段映射（`variant=a.variant.name`、`machine_shape=a.machine_shape.name`、`accelerator=a.accelerator.value`)、落盘、keep-alive 重拉、重建后 exec、重建后 stop。**没有任何一步报错**，兜底 `colab_unassign.py --execute` 未执行。
- token 结论：服务端给的是**新 token**（指纹不同、长度同为 222、`token_expires_in=3600`），证明接管不能靠旧名册残留，必须现调 `list_assignments`。
- 本次保留了备份里的 `kernel_id`/`session_id`，所以 exec 续的是原 kernel。真实事故里名册被 CLI 清空、若无备份，这两个字段只能填 `None`：exec 会在同一 VM 上起新 kernel（文件系统在、kernel 内存状态丢），这一点本次**未单独实测**，接管 SOP 应按「kernel 状态不可假设还在」写。
- 本次从丢失到重建完成约 5 秒。原 keep-alive 子进程每 60s 查一次名册，名册缺失即自退（`session_not_found`)；丢失后拖得越久 VM 越可能被 Google 回收，重建窗口按事故文档口径限时处理、失败即 unassign，本次结论不外推到「丢了很久还能接回」。

## 第二步：wenxi 环境恢复路径核查（未装环境、未烧 G4 CU）

核查方式：本机文件清单 + `scripts/ops/colab_h3_wenxi_host.py` 无付费干跑 + Drive 只读 `rclone ls/hashsum`。宿主干跑如实失败：`RuntimeError: missing inputs [.../vendor/colab-h3-rclone.gz, .../input/manifest.json] wheels=[]`。

### 齐全的（不用补）

- 脚本（`scripts/ops/`）：`colab_h3_wenxi_host.py`、`colab_h3_wenxi_install.py`、`colab_h3_wenxi_preflight.py`、`colab_h3_wenxi_phase.py`、`colab_h3_wenxi_models_copy.py`（无操作校验版）、`colab_h3_restore.py`、`colab_h3_preinstall_torch.py`、`h3_g4_identity.py`、`h3_g4_setup.py`、`h3_a100_phase_receipt.py`、`colab_h3_paid_watchdog.sh`，均在。
- 本机凭据/配置：`~/.config/rclone-h3/rclone.conf` 在；文戏模板 `templates/yz_h3_wenwu_test/variants/wenxi/workflow_api.json` 在。
- Drive 侧（只读实查）：`comfyui-h3-colab-dedicated/rental-20260924-5090/` 的 `source-only.tar`、`colab-stage2-runner.tar`、`model-parts/`（3 个分片大模型）和 `models/` 直存 10 文件在，含 2026-10-21 已并入主树的 7 个文戏模型（dmad/Combat/Fight_Flow/Motion_Repair/speed_slider/latent_upscaler/taeh3），即 restore 一次带全 13 模型这条路仍成立；`wenxi-setup/` 下历史 preflight/SMOKE 回执在。

### 缺口清单（本地 `.cache/colab_wenxi_setup/` 已被 2026-10-21 清理整目录删除）

| 缺什么 | 补法（均已验源） | 备注 |
|---|---|---|
| `vendor/colab-h3-rclone.gz` | Drive `standard-v1/runtime/bootstrap/rclone-v1.75.1-f66d8c1d.gz`（32,606,009 B，SHA-256 `e3c2c608…`)，拉下改名为宿主写死的文件名 | 宿主把它传到 VM 解压成 `/content/rclone`；改名后建议先在本机 `gzip -t` 验完整性 |
| `vendor/sageattention-2.2.0-cp313-cp313-linux_x86_64.whl` | Drive `standard-v1/runtime/g4-sm120/sageattention-2.2.0-cp313-cp313-linux_x86_64.whl`（15,482,615 B) | 已远程 hashsum 实测 `1cdc658e69315ce4…`，与 2026-10-21 记录的在用 wheel 一致；注意别拿 `rental-…/a100-perf-pilot/` 那个同名 wheel（SHA `36fb6b6f…`，是另一构建） |
| `input/manifest.json` 及整个 `input/`（assets、workflow_api.json、prompt 文件） | **无现成源，按《离婚后》每单元现生成** | 这是生产输入不是环境：manifest 记 class_types/model_files/assets/prompt 与 workflow 的 SHA，由拆包/接线产物打包；现行 `colab_h3_wenxi_phase.py` 还是写死一条 SMOKE（EP01-继母-v21-U01、固定种子）的形态 |
| 生产级宿主 | 现行 `colab_h3_wenxi_host.py` 只做「建环境 → preflight → 1 条 SMOKE → 停机」 | 《离婚后》批量生产需按事故文档口径另写/扩展：单一监督进程全程不退出、Drive 任务队列让 VM 自主领活、每 2–3 分钟轻量 exec 心跳、产物逐条 Drive 回执 |

### 完整建环境一次的估算（不开渲染）

依据 2026-10-21 冷启动验收轮（`runs/colab_wenxi_setup.md`，G4 8.90 CU/h）：identity 8.8s、preinstall 26.2s、restore 292.7s（并行分片版；旧串行版 727s）、setup 36.3s、wenxi_install 36.7s，preflight 另需对 13 个模型算 SHA（量级几十秒），加上 `colab new` 与上传（wheel+rclone+input tar，约 1 分钟内）。

- **只建环境到 preflight PASS：约 8–10 分钟墙钟，约 1.2–1.5 CU**（按 8.90 CU/h 折算；余额结算有滞后，实际扣费以停机后 `colab usage` 为准）。
- 若 restore 退回串行分片路径，restore 一项涨到约 12 分钟，整轮约 16 分钟、约 2 CU。
- 对照：含一条 smoke 的完整验收轮实测墙钟 823.6s、耗 1.84 CU（其中 smoke 服务端渲染 180.4s）。

## 后续生产建议的会话组织方式

1. **一个批次一个监督进程**：建会话 → 补 vendor/input → 装环境 → 全部单元 → 验收 → 停机，在同一个长命进程里做完，中途不退出；不再拆 start/run/fix 多段宿主靠「会话应该还在」衔接。
2. **guard 必挂**：会话一建好就起 `colab_orphan_guard.sh`，`AUTO_UNASSIGN=1`、心跳文件由监督进程每条产物（且至少每 2–3 分钟）touch；本次实验已验 guard 在 Active=0 时自退、不误杀。
3. **接管 SOP 入册**：名册丢失先停下按名重试，改走本次验证过的重建路径（CLI 解释器 → `list_assignments` → 按 endpoint 重建 `SessionState`（新 token，kernel 字段有备份用备份、无备份填 None 并默认 kernel 状态已丢）→ `StateStore` 落盘 → 重拉 keep-alive → exec 探针验 hostname）；限时几分钟，失败立刻 `colab_unassign.py --execute`，停机以 `colab usage` Active=0/rate=0 为准。建议平时把「会话名+endpoint」随心跳单独记一份在 `runs/`（不含 token），丢名册时不用靠备份猜 endpoint。
4. **干完即停、不留待命会话**；修复轮并进同一次监督运行或另开新会话。
5. 本次实验的含 token 备份文件已在收尾删除；`.cache/colab_takeover_test/` 只留日志与脚本（共 76K，无大文件），按任务级缓存口径后续可整目录清。

## 证据与收尾状态

- 步骤日志：`.cache/colab_takeover_test/steps.log`；重建日志 `rebuild.log`；guard 日志 `orphan_guard.log`（`active=0, guard exit`)。
- 最终复查（报告落笔前）：`colab usage` balance 956.91、rate 0.00/hr、Active 0；`~/.config/colab-cli/sessions.json` 为 `{}`；无残留 colab/guard/监督进程。
- 本任务未触碰 `.cache/lihun*`、`jobs/`，未做 git 提交，未打印任何 token/密码明文（日志中只有 token 的 SHA-256 前 12 位指纹）。
