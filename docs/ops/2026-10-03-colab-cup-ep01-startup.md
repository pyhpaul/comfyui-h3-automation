# 2026-10-03 Colab 制作奶茶 EP01：启动失败与续跑

这杯奶茶你请不起 EP01，走主干 Colab G4 工作流。合同是只一采、`motion_latent`、9:16、15.083 秒、24fps、12 步。入口是 `scripts/ops/colab_h3_cup_ep01_host.py`，付费必须显式 `--execute-paid`。单次上限 4 小时 / 40 CU。恢复用串行 `colab_h3_restore.py`，不改成四并发快速恢复。

只有 U04 读取 U03 的运动潜变量。U01、U02、U03、U05、U06、U07、U08、U09 都是独立开场。新虚拟机不能沿用旧卡上的 latent。不要同时再开一张 G4。

素材清单：`docs/ops/drive-cup-ep01-v1.json`。Drive 上的 job 包 sha256 前缀 `3ab91ccf1728fc9f`。账号、rclone 配置、密码和原始会话日志不入库。

## 成片归档

整集完成后，成片按飞牛 skill（`.cursor/skills/comfy-h3-feiniu/SKILL.md`）直接放入，不打 zip：

```text
H3_comfyUI_5090/archive/这杯奶茶你请不起（10.3）/EP01/U01/
...
H3_comfyUI_5090/archive/这杯奶茶你请不起（10.3）/EP01/U09/
```

每个单元目录放该条 mp4、latent（safetensors）、`prompt_h3.txt` 和 `run_meta.json`。远端大小已经一致就跳过。不要改共享根上的 `测试H3资产包`。

写这份记录时，U01–U04 已在会话 `h3-cup-ep01-20261003-164142` 出片；续跑会话 `h3-cup-ep01-20261003-174223` 正在做 U05–U09。九镜都完成后才往飞牛 archive 放最终成片。

## 启动时实际碰到的问题

### 1. 阶段标记用 `dict.get` 的默认值，传输阶段直接 KeyError

会话 `h3-cup-ep01-20261003-161734`。身份检查已通过，传输脚本也打印了成功行，主机随后退出。

`markers.get(name, STAGE_MARKERS[name])` 会先计算第二个参数。`transport` 不在 `STAGE_MARKERS` 里，所以即使前面准备了覆盖字典，也会在查找时抛出 KeyError。

修复：`markers.get(name) or STAGE_MARKERS[name]`。传输阶段的成功字符串仍是 `TEST2_TRANSPORT_READY`，因为复用的传输脚本就打印这一行。输入阶段的成功字符串是 `CUP_EP01_INPUTS_READY`。

这次大约用了 0.11 CU（余额 83.73 到 83.62）。会话已停，没有出片。

### 2. 子进程导入了冻结的 Test2 媒体模块

会话 `h3-cup-ep01-20261003-161919`。串行恢复约 798 秒，Comfy 就绪之后 U01 在约 9 秒内失败。

子进程写的是 `from h3_test2_ep01_media import inspect_latent, inspect_video`。那个模块再导入 `h3_test2_ep01_contract`，而主机没有把 Test2 合约上传到虚拟机。错误是 `ModuleNotFoundError: No module named 'h3_test2_ep01_contract'`。Drive 上的 `runner.log` 只有这一段。主机接着 `rclone cat` 还不存在的 `validation.json`，退出码 3。

同一会话里，setup 在真正执行前丢过一次连接。日志里同时有 `runtime.execute_code(`、`os.chdir('/content')` 和 `RuntimeError: Connection was lost.`，并且还没有 `RUN ` 时，把日志改名为 `*-preexec-lost.log`，等 10 秒再执行一次。这次重连成功，打印 `CUP_STAGE_PREEXEC_RECONNECT`，之后才到 `comfy_ready`。

修复：新增 `h3_cup_ep01_media.py`，改为导入 `h3_cup_ep01_contract`。子进程和 `EXTRA_UPLOADS` 都指向 `/content/h3_cup_ep01_media.py`。不要改冻结的 `h3_test2_ep01_media.py`，也不要让 Test2 主机去跑这集。

失败时余额读数是 81.55，当时仍在按 8.90 CU/小时计费。会话已停，没有出片。

### 3. 小文件 `colab upload` 卡住，90 秒超时拆掉整张卡

会话 `h3-cup-ep01-20261003-163830`。前面 9 个小文件都传完了。`h3_a100_media.py` 只有 2633 字节，上传日志里只有 CLI 的版本提示，90 秒内没有 `Uploaded`。主机把付费会话停掉。

修复：同一次会话里对这一次上传再试一次，第二次超时 180 秒。卡住的日志改名为 `*-timeout.log`，并打印 `CUP_UPLOAD_RETRY`。不要因为一次上传卡住就重新开一张卡、再付一次模型恢复。

### 4. 接了父潜变量的成片短于 15 秒，尾帧文件没写出来

会话 `h3-cup-ep01-20261003-164142`。U01–U04 都生成成功。接触表、首帧和成片都是单幅 768×1376，没有上下分屏。

U04 接 U03，按合同丢掉 22 帧重叠，成片是 340 帧、14.17 秒。审核截帧用 `ffmpeg -ss 15.0` 抽尾帧，这个时间点在片长外面，`last-frame.jpg` 没有落盘。接触表和首帧已经在 Drive 上。主机 `rclone copyto` 尾帧失败（directory not found）后，`finally` 停掉会话。U05–U09 因此没跑。

从成片用 `-sseof` 抽出的最后一帧仍是单幅画面。尾帧缺失不是分屏。

修复：尾帧改为 `-sseof -0.15`，并且文件必须存在，否则子进程失败。主机拉不到 `last-frame.jpg` 时打印 `CUP_REVIEW_LAST_FRAME_MISSING`，不再为此停卡。续跑只能从没有父镜的单元开始：`--start-unit U05`。U04 不能这样续，因为它的父潜变量不在新虚拟机的本地输出目录里。

### 5. 回执轮询超时，阶段本身是成功的

U03 和 U04 都出现过 `PHASE_RECONCILED_STOP_NO_RETRY`，`receipt_error` 是 `TimeoutExpired`。紧接着的 `CUP_EP01_PHASE_RESULT` 是 `state: success`，Drive 上的 `phase.json` 和 `validation.json` 也通过了主机校验。这不是失败，不要为同一镜再交一次 prompt。

## 续跑

会话 `h3-cup-ep01-20261003-174223`，命令带 `--execute-paid --start-unit U05`。

串行恢复 641.97 秒、6 个模型。恢复结束时余额从 73.15 读到 71.54，速率 8.90 CU/小时，一张卡在计费。GPU 是 NVIDIA RTX PRO 6000 Blackwell Server Edition，capability 12.0。预检打印 `PREFLIGHT_OK`。输入校验打印 `CUP_EP01_INPUTS_READY`，核对的是奶茶 job 包的 sha256。

预检日志里的 `char-012`、`scene-013`、`prop-016` 来自冻结的 EP04 U02 样本（`h3_a100_ab_preflight.py`），不是这集奶茶的参考图。

## 相关文件

- `scripts/ops/colab_h3_cup_ep01_host.py`
- `scripts/ops/h3_cup_ep01_contract.py`
- `scripts/ops/h3_cup_ep01_inputs.py`
- `scripts/ops/h3_cup_ep01_media.py`
- `scripts/ops/h3_cup_ep01_child.py`
- `scripts/ops/h3_cup_ep01_phase.py`
- `docs/ops/drive-cup-ep01-v1.json`
