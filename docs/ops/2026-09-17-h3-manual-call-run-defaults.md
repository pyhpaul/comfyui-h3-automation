# H3 manual-call 出片默认参数（固化）

**日期：** 2026-09-17  
**适用范围：** EP04/EP05/EP06 等 `h3_manual_call_ep07_v2_1_layout` + `ep08_v4_6_*` 手动调用包，经 `jobs/ep_units` 串行出片。

与「Comfy 启动 / vm122 隧道」分开：见 `2026-09-17-comfy-h3-canonical-start.md`。

## 默认渲染参数（上次 EP04 成功批）

| 项 | 值 | 说明 |
|----|-----|------|
| continuity | `motion_latent` | 跨 U 用一采 AV latent，不挂父 MP4 |
| second_pass | **关** | 不要加 `--second-pass` |
| gpu_profile | `auto` | 5090→minimax sage；4080→bypass |
| aspect_ratio | `9:16 (Portrait Widescreen)` | job 字段 |
| megapixels | `1.0` | job 字段 |
| COMFY_BASE_URL | `http://192.168.5.122:8190` | 经 vm122 |

对应命令（或 `scripts/ops/run_ep_manual_call_defaults.sh`）：

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
python scripts/run_ep_units_profiled.py \
  --units U01 U02 ... \
  --continuity motion_latent \
  --gpu-profile auto \
  --job-glob "EP04-H3-manual-v16-{unit}" \
  --download-dir /mnt/c/Users/lxy/Downloads/<batch-dir> \
  --batch-log runs/<batch>.json
```

**不要**默认开 `--second-pass`（那是因果验收 B 模式，产物带 pass2）。

## 审核门禁（入队前）

1. 包 → job 后 `scripts/audit_pack_prompts.py --glob '…-U*'` 全 PASS  
2. 提示词：wire-only（`@`→`<Picture N>`）；「沿用」单元可补 `绑定资产` 行，**镜头正文不得改**  
3. 参考图：上传清单 `asset_id` 与 staged `idN-*` 文件名对应；无缺文件 / unbound（文内「不绑定」除外）

## 环境变量备忘

可放本机（勿提交密码）：

```bash
# scripts/ops/h3_manual_call_run_defaults.env.example
export COMFY_BASE_URL=http://192.168.5.122:8190
export COMFY_GPU_PROFILE=auto
# run wrapper 固定：CONTINUITY=motion_latent  SECOND_PASS=0
```
