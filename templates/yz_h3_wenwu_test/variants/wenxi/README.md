# 文戏版（wenxi）— 基于 yz_h3_wenwu_test 的派生模板

从 `templates/yz_h3_wenwu_test/workflow_api.json` 程序化派生：加载原 JSON、仅改 3 个
`LoraLoaderModelOnly.strength_model` 后写出。节点不删、不增、不重连（武戏 LoRA 以
strength=0 关闭，保留节点便于与原模板逐节点对照、随时改回）。原模板与 bindings 未改；
`bindings.yaml` 的 prompt/参考图绑定节点（263/51/49/50/43/19/23/199/200/201/259/252/364）
全部原样，runner 仍按原 bindings 注入。

## 完整节点链

模型链：
`192 UNETLoader`（minimax_h3_hybrid_fl2va_ref2va_b25-49-int8, default）
→ `53 LoraLoaderModelOnly`（minimax_h3_dmad_full_dareties_v4_step600, **0.8**）
→ `400 LoraLoaderModelOnly`（MysticXXX_MMH3-V1, **0.35**）
→ `342 LoraLoaderModelOnly`（H3_Combat_V2, **0.0 ← 改**）
→ `344 LoraLoaderModelOnly`（Motion_Repair_V2, **0.35 不变**）
→ `345 LoraLoaderModelOnly`（H3_Fight_Flow_V1, **0.0 ← 改**）
→ `343 LoraLoaderModelOnly`（motion_speed_slider_mmh3_v1.1, **0.0 ← 改**）
→ `331 ModelAttentionBackend`（comfy kitchen attention）
→ `332 BlockSparseAttention`（sol-attn, tau 1.3, 0.2–1.0, min_tokens 12288）
→ `333 MiniMaxH3SigmaShift`（shift_video 12, shift_audio 3.0）
→ `401 MiniMaxChunkFeedForward`（chunks 2, seq_threshold 4096）
→ `403 MiniMaxLowVRAMAttention`（head_chunks 4）
→ `329 ModelPreviewOverrideKJ`（vae=36, max_resolution 1024, tiny_vae taeh3）
→ `397 SelfLiftH3Sampler`（model=329）

条件链：`38 CLIPLoader`（qwen3vl_32b_minimax_h3_nvfp4_awq, minimax）
+ `36 VAELoader`（video int8）+ `37 VAELoader`（audio fp32）
→ `265 MiniMaxH3ReferenceToVideo`（ref_image 51/49/50/43/19/23/199/200/201、
ref_video 27/25/26、ref_audio 48/14/15、1344×768、length 124、ref_image_size match）
→ positive 直入 397；`328 ConditioningZeroOut`（←265）→ negative 入 397；
latent 取 265 输出 1。

采样：`255 KSamplerSelect`（euler）、`261 BasicScheduler`（model=329, simple, steps 10,
denoise 1）→ 397。`397 SelfLiftH3Sampler`：seed 905138662823835（固定）、cfg 1、
transition_step 6、lowres_scale 0.6、rho 0、w 0.5–1、upscaler_model
minimax_h3_latent_upscaler_3d_fp16.safetensors、highres_tiling false、upscaler_unload true。

解码/输出：397 → `253 VAEDecode`（vae 36）+ `254 VAEDecodeAudio`（vae 37）
→ `364 VHS_VideoCombine`（24fps, h264-mp4, crf 19, prefix `YZ_H3_`）；
397 → `9001 MiniMaxH3MotionContextSaveLatent`（`h3_context/wenwu_test`, clip_index 1）
→ `9002 PreviewAny`。时长/画幅辅助节点 259/250/252/366 与原模板一致，未动。

## 与原模板 diff

| 节点 | 参数 | 原值 → 新值 | 为什么 |
|---|---|---|---|
| 342 H3_Combat_V2 | strength_model | 0.65 → 0.0 | 武戏专用（打斗招式/受击），文戏注入会凭空加攻击性动作与肢体幅度，直接关断 |
| 345 H3_Fight_Flow_V1 | strength_model | 0.35 → 0.0 | 武戏专用（打斗连贯/攻防节奏），文戏会把走位、转身拉向交战步态，关断 |
| 343 motion_speed_slider | strength_model | 3.0 → 0.0 | 见下 |
| 344 Motion_Repair_V2 | strength_model | 0.35 → 0.35（保留） | 见下 |

**motion_speed_slider 取 0.0 的理由**：`LoraLoaderModelOnly.strength_model` 是 LoRA
注入权重，不是速度倍率——0 才是「无注入、模型原生节奏」这个中性点，1.0 仍在持续
提速。原 3.0 是为打斗抢拍的强提速；文戏以对白、口型、微表情、慢动作幅度为主，
提速会造成抢话感、手势赶拍、镜头内动作密度虚高。故归零。若实测人物过于僵硬，
只小步试 0.5，不要直接回 1.0 以上。

**Motion_Repair_V2 保留 0.35 的理由**：其职责是通用运动修复（抖动、手部/时序
伪影），不是武戏语义 LoRA。文戏同样有抬手、持物、转头、口型联动，去掉它收益
（无打斗收益可言）小于画面稳定性损失，故与原值一致保留。

其余 LoRA（53 DMAD 0.8、400 MysticXXX 0.35）、采样、SelfLift、解码、存 latent
全部与原模板一致。

## 文戏使用说明

- 适用：对白、情感、室内日常、慢节奏走位等无打斗/追逐/兵器动作的单元。
- 不适用：打斗、追逐、快速舞蹈、大幅肢体冲突——用回原 `yz_h3_wenwu_test` 模板。
- 本目录只有 `workflow_api.json`，无独立 bindings：runner 若按模板目录找 bindings，
  需指向原模板的 `bindings.yaml`（绑定节点号未变，可直接复用），或把本文件作为
  workflow 覆盖传入，不要改绑定位号。
- 接力与原模板一致：9001 照常存 motion latent，场景连续仍走 `motion_latent`；
  本变体只改模型味，不改接力方式。
- 切换回武戏只需把 342/345/343 改回 0.65/0.35/3.0（或直接用原模板），勿两套混跑同一链。

## 校验结果摘要

程序化 diff 校验（python 加载两份 JSON 递归对比）：

```text
parse_ok=True orig_nodes=46 wenxi_nodes=46 same_ids=True
DIFF 343.inputs.strength_model: 3.0000000000000004 -> 0.0
DIFF 342.inputs.strength_model: 0.6500000000000001 -> 0.0
DIFF 345.inputs.strength_model: 0.3500000000000001 -> 0.0
total_diffs=3
only_expected= True
```

即：JSON 可解析、节点数/ID 与原模板一致、除上述 3 个目标参数外零差异。
