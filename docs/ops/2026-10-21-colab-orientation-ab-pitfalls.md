# Colab 方位 A/B 记录：三次提交前失败与修复

**日期：** 2026-10-21（潮缚 EP01-潮缚-v2-U01 方位 A/B：A=罗盘原文 vs B=逐镜画面坐标）
**结论：** 三次失败全部死在**提交生成之前**，零 prompt、零废片；其中两次是 Colab
通道瞬断（上传 SSL、exec WebSocket），一次是宿主脚本回执路径拼接 bug（确定性，
与网络无关）。三个修复均已写进子 agent 的宿主脚本并经第四次会话实测：
打包上传+重试、exec 瞬断重试、回执路径补会话段。第四次已过 preflight 宿主核验
并提交 A1。最终 A/B 结论见子 agent 报告 `runs/orientation_ab_colab_ep01u01.md`（待出）。

> 原始证据在本地 `.cache/orientation_ab/`（未进 git）：`host_run{1,2,3,4}.log`
> 与每次会话目录 `h3-orient-<session>/`（stop.log、cu-snapshots.jsonl、
> stage-timing.jsonl、colab-session.jsonl、evidence/preflight.json）。
> `runs/` 被 .gitignore 忽略，故本文件为唯一入库记录。

## 坑 1：逐文件 `colab upload` 时 HTTPS 瞬断（会话 070701，00:07–00:10）

- 死点：逐个上传输入图，第一张角色图即 exit 1，尚未开始 restore。
- 证据：`upload-input-asset_0_id0-char-001-w01.png.log` 原文
  `SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in
  violation of protocol')`，Colab 代理连接中途断开。
- 排除：同一批文件之后改打包上传全部成功，文件本身无问题。
- 修复：全部输入打成单个 `orient_input.tar.gz` 一次上传，失败自动重试 3 次，
  远端解包（bundle+mover）。第二次起上传均一次通过。

## 坑 2：回执路径少拼会话段，preflight 全过仍停机（会话 071220，00:12–00:30）

- 死点：restore（894s）+ setup + preflight 全过（16 个 SHA256 全 match、
  `ORIENT_PREFLIGHT_OK 16`、设备 RTX PRO 6000）之后，宿主在提交 phase 前抛错停机。
- 证据：`host_run2.log` traceback ——
  `colab_h3_a100_ab_host.remote_manifest_sha256` 执行
  `rclone cat h3drive_h3:comfyui-h3-colab-dedicated/orientation-ab-ep01u01/preflight.json`
  返回 exit 3（directory not found）。
- 根因（读代码坐实）：该函数以 `receipt_path.rsplit("/", 2)[0] + "/preflight.json"`
  反推 preflight 在 Drive 上的路径；当时宿主传入的 `receipt_path` 少了
  `<session>` 一段，反推出 `orientation-ab-ep01u01/preflight.json`，
  而 preflight 实际上传到 `orientation-ab-ep01u01/<session>/preflight.json`。
  属本仓库宿主脚本的路径契约不一致，非 Colab/网络问题。
- 修复：`receipt_path` 改为 `f"{remote}/ORIENT/phase.json"`（`remote` 已含
  `<session>` 段）；`remote_json` 拉取失败重试 3 次；phase 本身报错时不直接
  判死，改以远端回执核验（state/session/label/manifest sha）为准。
- 验证：第四次会话打出 `HOST_PREFLIGHT_VERIFIED 16`，本坑关闭。

## 坑 3：`colab exec` 的 WebSocket 在身份确认阶段断开（会话 074047，00:40–00:43）

- 死点：第一步 identity 即抛
  `WebSocketConnectionClosedException: socket is already closed`
  （`host_run3.log` / `identity.log`），restore 未开始。
- 定性：Colab CLI 执行通道瞬断；第四次同一步骤原样通过，无代码错误。
- 修复：新增 `exec_retry` 包裹 mover/identity/preinstall/restore/setup/preflight，
  命中 WebSocket/SSL 类错误（`WebSocketConnectionClosedException`、`SSLError`、
  `Connection was lost`、`SSLEOFError`）时隔 10 秒自动重试 1 次。

## 费用与停机纪律（均已遵守）

- 余额 1003.71 → 第四次 preflight 后 998.93 CU，累计约 4.8 CU；
  大头是失败 2 的 restore 约 15 分钟（8.9 CU/hr）。
- 每次失败后均验证 `Active assignments: 0`、计费归零（stop.log /
  sessions-after-stop.log / `colab usage`）才算收尾。

## 下次跑 Colab A/B 前的检查单

1. 输入只走单 tar 包上传 + 重试，不要逐文件 `colab upload`。
2. 所有 `colab exec` 阶段走带瞬断重试的封装，不要裸调。
3. phase 的 `receipt_path` 必须与远端脚本实际发布路径逐段一致（含 session 段）；
   提交前先人工对一遍 `remote_manifest_sha256` 的反推结果。
4. preflight 必须远端真 PASS 且宿主二次核验后才许提交（本次做到，继续保持）。
5. 任何失败先确认会话已停、计费归零，再谈重试；不要在旧会话未停时新开会话。

## 待办（A/B 跑完后）

- [ ] 子 agent 的 `orient_host.py` / `orient_phase.py` / `orient_preflight.py`
      目前只在 `.cache/orientation_ab/scripts/`；待 phase 回执核验通过后回收进
      `scripts/ops/`（注意其中 `ROOT.parents[3]` 与 `.cache` 输入路径的耦合，
      回收时一并改干净），另做一次提交。
- [ ] 最终报告 `runs/orientation_ab_colab_ep01u01.md` 出后，把 A/B 结论摘要补进本文件。
