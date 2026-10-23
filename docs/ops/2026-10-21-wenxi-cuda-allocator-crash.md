# 文戏链 CUDA 崩溃记录：SelfLift × cudaMallocAsync

**日期：** 2026-10-20（EP23 试点首次复现）/ 2026-10-21（潮缚 EP01 V2 再次复现后固化）
**结论：** 文戏（wenxi / SelfLift）链路必须用原生 CUDA 分配器启动 Comfy，即
`--disable-cuda-malloc`。原工作流两种分配器都能跑。已固化进
`scripts/ops/comfy_gpu_start.sh`（`H3_DISABLE_CUDA_MALLOC`，默认 1）。

## 症状

- 文戏任务采样中途编排端报 `Server disconnected without sending a response`
  （httpx RemoteProtocolError / `comfy_orch.errors.ConnectionFailed`）。
- vm106 隧道进程仍在监听，但转发日志刷 `Secsh channel open FAILED:
  Connection refused`——后端 `127.0.0.1:8188` 已无进程，看起来像“环境断开”，
  实际是卡上 Comfy 进程崩溃退出。
- 崩溃后 `/queue`、`/history/{prompt_id}` 都查不到该任务（历史在内存里，
  随进程一起没了）；该条按“丢失”处理，只重交一次，不要连环重交。

## 崩溃签名（租卡 `comfyUI-h3.log`）

文戏 U01（潮缚 EP01 V2，prompt `f6dcefdc-…`）走到 SelfLift 高清段第 2/4 步：

```text
BlockSparseAttention: sparse producer path: 126640 tokens, sinks (0, 254)/(234, 254)
[SelfLift timing] high_resolution step 1/4 ...
[cudaMallocAsync] recovered from an allocation failure by trimming the pool and retrying.
terminate called after throwing an instance of 'c10::AcceleratorError'
  what():  CUDA error: invalid argument
Returning 1 (CUDA_ERROR_INVALID_VALUE) from cuMemFreeAsync
Fatal Python error: Aborted
```

堆栈在 `comfy_extras/nodes_sparse_attention.py` 的 `block_patch` 与
`comfyui-SelfLift` 的 `progressive_sample` 里。低清段（6 步，55164 tokens）
能过，崩在潜变量放大后的高清稀疏采样（126640 tokens）。

## 根因

工作流触发、配置引爆：

- **触发方是文戏工作流**：`templates/yz_h3_wenwu_test` 的 wenxi 变体用
  SelfLift 两段式（低清采样 → LatentResizer3D 放大 → 高清 BlockSparseAttention
  采样）。原工作流没有这条路径，用的是单段采样 +
  MiniMaxH3MemoryEfficientSageAttentionPatch。
- **引爆方是 cudaMallocAsync 分配器**：稀疏注意力在大 token 量下频繁申请/
  释放显存；异步池裁池（trim）后又释放已失效的异步分配，
  `cuMemFreeAsync` 返回 `CUDA_ERROR_INVALID_VALUE`，进程 abort。
- 不是提示词/资产问题（崩在采样，不在加载），不是卡坏了（同一张卡、
  同一配置下原工作流正常出片），也不是纯显存 OOM（日志是先“裁池恢复”
  再非法释放）。

## 对照证据（同单元、同父 latent、同提示词，只改分配器）

| 试点 | 分配器（`system_stats` 设备名后缀） | 结果 |
|------|------|------|
| EP23-U05 文戏试点 1、2 | `cudaMallocAsync` | 同签名崩溃，Comfy 进程退出 |
| EP23-U05 文戏试点 3 | `native`（`--disable-cuda-malloc`） | 成功，243s，产物进飞牛 |
| 潮缚 EP01 V2 文戏 U01（8191 新卡） | `cudaMallocAsync` | 高清段第 2 步同签名崩溃 |
| 同上，改原生分配器重启后 | `native` | 恢复运行 |

日志样本：`runs/chaofu_wenxi_pilot{,2,3}.log`、
`runs/chaofu_ep01_v2_interleave.log`（runs/ 不入库，为本地样例）。

## 处置与预防

1. 正式启动脚本默认带 `--disable-cuda-malloc`
   （`scripts/ops/comfy_gpu_start.sh`，可用 `H3_DISABLE_CUDA_MALLOC=0`
   临时关掉做 A/B，但不要用异步分配器跑文戏链）。
2. 通过 `remote_comfy_h3.sh restart` 上传的 `/root/start_comfy_h3.sh`
   与仓库脚本同内容，换卡开机自动生效。
3. 验证看设备名后缀：`GET /system_stats` 的 devices 应为
   `NVIDIA GeForce RTX 5090 : native`；显示 `cudaMallocAsync` 时不要入文戏链。
4. 现场若只把 Comfy 手工带 `--disable-cuda-malloc` 起在某台卡上
   （如 2026-10-21 潮缚 EP01 的 8191 卡），换卡后以脚本为准，不要依赖
   手工命令的历史进程。
5. 代价：原生分配显存碎片略多、速度可能略慢；可接受。原工作流不受影响，
   两条链共用一个原生分配器的 Comfy 即可，不需要为双链起两个实例。

## 关联

- 正式启动：`docs/ops/2026-09-17-comfy-h3-canonical-start.md`
- 文戏驱动：`scripts/run_chaofu_wenxi.py`
- 隧道是 vm106 上的独立转发进程；后端崩溃时先查租卡
  `comfyUI-h3.log` 与 8188 监听，不要先重建隧道。
