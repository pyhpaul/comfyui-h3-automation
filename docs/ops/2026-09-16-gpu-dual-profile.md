# GPU 双节点适配（5090 主 / 4080 备）

同一套 `yz_h3_ep_unit` 模板，按卡切换注意力补丁，避免 4080 上 MiniMax FP8 Sage 报
`cudaErrorNoKernelImageForDevice`。

| Profile | 识别 | 注意力节点 | 用途 |
|---------|------|------------|------|
| **rtx5090** | doctor 名含 `5090` | `MiniMaxH3MemoryEfficientSageAttentionPatch`（模板原样） | 主节点 |
| **rtx4080** | 含 `4080`/`4090`，或未知卡 | **bypass**（去掉 Sage，UNET→LoRA 直连；可改 `sage_fp16`/`flash`） | 备用节点 |

入口：`comfy_orch.gpu_adapt`；`scripts/run_ep_units_profiled.py --gpu-profile auto|rtx5090|rtx4080`  
环境变量：`COMFY_GPU_PROFILE`（默认 `auto`）。

```bash
export COMFY_BASE_URL=http://192.168.5.122:8190
# 自动按 doctor 选卡；也可强制：
# export COMFY_GPU_PROFILE=rtx4080

python scripts/run_ep_units_profiled.py --units U01 \
  --continuity motion_latent \
  --job-glob "EP04-H3-manual-v13-{unit}" \
  --download-dir /mnt/c/Users/lxy/Downloads/EP04-manual-v13-U01-latent-mc
```

doctor 行会打印 `gpu_profile=rtx4080(bypass)` 或 `rtx5090(minimax_sage_fp8)`。

本机实测：4080 上 MiniMax FP8 Sage → `NoKernelImage`；`PatchFlashAttentionKJ` → 未装 FA2/FA3。默认 bypass 最稳。
