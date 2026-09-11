# 租卡 ComfyUI 实环境与 API 归档

**日期：** 2026-09-09  
**状态：** 已在实机验证（编排用 HTTP API + smoke 闭环；YZ 修补图仅校验入队）  
**保密：** 本文不存放 SSH 密码。密码若曾在聊天中出现，应轮换并改为密钥登录。

## 1. 租卡主机

| 项 | 值 |
|----|-----|
| SSH | `ssh root@6d6f8fd977eb4c58ba2856d5982c68ae71.gz14.chenyu.cn -p 26301` |
| 容器/主机名（当时） | `8a080cb76b9a` |
| GPU | NVIDIA GeForce RTX 5090 |
| ComfyUI 路径 | `/root/ComfyUI`（另有 `/root/autodl-tmp/ComfyUI`） |
| Comfy 启动（当时） | 租卡侧已监听（实测 `0.0.0.0:8188`，`python3` pid 见开机后进程） |
| Comfy 版本 | 约 `0.33.0`（frontend 约 `1.49.6`；以当日 `/system_stats` 为准） |
| 监听 | 租卡本机 `:8188`（公网仍建议经 vm122 `8190` 隧道访问） |

> **换机提醒：** 租卡每日开机可能换域名/端口。更新 vm122 `/tmp/comfy_ssh_forward.py` 的 `SSH_HOST`/`SSH_PORT` 与 `/tmp/.comfy_gpu_ssh_pass`（权限 600），重启转发后验证 `http://192.168.5.122:8190/system_stats`。**不要把密码写入仓库。**

同机其它常见端口（平台映射，非 Comfy）：`8888` Jupyter、`7860` cyui、`9999` gopeed、`22` sshd。

## 2. 经 vm122 的端口映射（当前推荐访问方式）

| 项 | 值 |
|----|-----|
| 对外 URL | `http://192.168.5.122:8190` |
| 含义 | vm122 `0.0.0.0:8190` → SSH 隧道 → 租卡 `127.0.0.1:8188` |
| 编排变量 | `export COMFY_BASE_URL=http://192.168.5.122:8190` |

### 转发进程（运维备忘）

曾在 **vm122** 上用用户态脚本常驻转发：

- 脚本：`/tmp/comfy_ssh_forward.py`
- venv：`/tmp/comfy-fwd-venv`
- 密码文件（权限 600，勿提交仓库）：`/tmp/.comfy_gpu_ssh_pass`
- 日志：`/tmp/comfy_ssh_forward.log`

进程掉线后需在 vm122 上重新拉起；长期应改为 **SSH 公钥** + `systemd`/`autossh`，不要把密码放进 argv。

本机 WSL 也可另开：`ssh -L 127.0.0.1:8190:127.0.0.1:8188 -p 21017 root@<host>`（需交互或密钥）。

## 3. YZ 工作流 API 导出结论

| 文件 | 说明 |
|------|------|
| UI 工作流 | `C:\Users\lxy\Downloads\YZ金鱼-MiniMax+H3-多参考生视频-优化版.json` |
| 前端 Export API | `C:\Users\lxy\Downloads\YZ金鱼-MiniMax+H3-多参考生视频-优化版-api.json` |

**现象：** 即使在可用租卡环境导出，部分自定义节点仍缺 `class_type`、出现 `UNKNOWN`（典型：`Text` id 263、`MiniMaxH3MemoryEfficientSageAttentionPatch` id 58、以及「忽略多组孤海」空壳）。

**原因：** 浏览器 Export 序列化不完整，不是「租卡缺节点」。实机 `object_info` 可查到：

- `Text`（kaytool，`inputs.text`）
- `MiniMaxH3ReferenceToVideo`
- `MiniMaxH3MemoryEfficientSageAttentionPatch`
- `VHS_LoadVideo` 等

**处理：** 按 UI 节点类型 + `GET /object_info/<name>` 修补后得到可提交图；校验稿路径（gitignore）：

`.scratch/yz_repaired_api.json`

官方没有单独的「服务器导出 API JSON」HTTP 接口；备选真相来源是成功任务的 `GET /history/{prompt_id}` 内 `prompt`。

## 4. 实机 API 实测（2026-09-09）

目标：`COMFY_BASE_URL=http://192.168.5.122:8190`

### 4.1 内置 HTTP（16/16 PASS）

- `GET /system_stats`
- `GET /embeddings`
- `GET /models`
- `GET /queue`
- `GET /history`、`GET /history/{prompt_id}`
- `GET /object_info/LoadImage`
- `GET /features`
- `GET /extensions`
- `POST /upload/image`
- `POST /prompt`（迷你 LoadImage→SaveImage，完整跑通）
- `GET /view`（拉回 PNG）
- `POST /interrupt`
- `POST /queue`（`clear: true`）
- `POST /prompt`（YZ **修补图**，`node_errors: {}` 后立即 interrupt，未跑完整 H3）
- `POST /free`

### 4.2 comfy-orch 闭环

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
comfy-orch doctor          # OK
comfy-orch submit <smoke_passthrough job>
# 例：job_id c43baaf204ef → outputs/.../comfy_orch_smoke_00001_.png
```

### 4.3 租卡 input 素材（YZ 导出图内引用，当时存在）

- `01_U05-director-control-map-v8.png`
- `02_scene-002-v3.png`
- `03_char-001.png`
- `04_char-003-v5.png`
- `05_char-004.png`
- `06_prop-001-v4.png`
- `video_01_U05_motion_reference.mp4`

## 5. 本地 CPU 冒烟机（已停用）

| 项 | 值 |
|----|-----|
| Host | `vm122` / `192.168.5.122` |
| 原 Comfy | `http://192.168.5.122:8188`（`--listen 0.0.0.0 --cpu`） |
| 状态 | **2026-09-10 已停掉进程并清理**；无 systemd/supervisor 常驻单元。后续统一走 `:8190` 租卡。 |

与租卡区分（历史）：CPU=`8188`（已停），租卡隧道=`8190`（现行）。

## 6. 前端可见性（方案 B）

API 提交的任务在 Comfy 网页 **「0 个活动任务」→ 任务队列 → 全部/今天** 中查看；**不会**回填画布控件。详见：

`docs/superpowers/specs/2026-09-08-comfy-ui-visible-feedback-no-extension-design.md`

## 7. 后续待办（未归档为已完成）

1. 将 `.scratch/yz_repaired_api.json` 收成正式 `templates/yz_*/workflow_api.json` + `bindings.yaml`
2. 租卡上跑一条完整 YZ 出片并拉回 `outputs/`
3. SSH 改为密钥 + 持久化隧道服务；轮换曾暴露的密码
4. 可选：用手跑成功的 `/history/{prompt_id}` 作为 API 真相源，与修补稿对比
