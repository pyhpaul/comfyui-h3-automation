# 武戏版（wuxi）— wenwu 模板固化变体

> 状态：**固化副本，只固化、不改值**。与原模板 `templates/yz_h3_wenwu_test/workflow_api.json` 逐节点参数完全一致（校验见文末）。所有「建议值」只写在本 README 的可选调参表里，**未**写进 `workflow_api.json`。
> 注意：runner `scripts/run_wenwu_test_ep_units.py` 仍以 `TEMPLATE = "yz_h3_wenwu_test"` 读取原模板目录，本变体目录目前是独立的固化/文档副本，runner 不会自动改读这里；要让变体生效需另行改 runner 的模板指向（不在本次交付范围内）。

## 1. 完整节点链

### 1.1 模型主链（顺序即 LoRA 叠加顺序，后叠的覆盖/叠加先叠的）

```text
192 UNETLoader
  minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors, weight_dtype=default
→ 53  LoraLoaderModelOnly  minimax_h3_dmad_full_dareties_v4_step600_comfy_fro.safetensors @ 0.8
→ 400 LoraLoaderModelOnly  MysticXXX_MMH3-V1.safetensors @ 0.35
→ 342 LoraLoaderModelOnly  H3_Combat_V2.safetensors @ 0.65        ★武戏核心
→ 344 LoraLoaderModelOnly  Motion_Repair_V2.safetensors @ 0.35    ★武戏修复
→ 345 LoraLoaderModelOnly  H3_Fight_Flow_V1.safetensors @ 0.35    ★武戏连贯
→ 343 LoraLoaderModelOnly  motion_speed_slider_mmh3_v1.1.safetensors @ 3.0  ★武戏速度
→ 331 ModelAttentionBackend     attention=comfy kitchen attention
→ 332 BlockSparseAttention      selection=sol-attn, tau=1.3, start_percent=0.2, end_percent=1,
                                min_tokens=12288, extra_tokens=256, sink_conditioning=exact_kv_and_rows
→ 333 MiniMaxH3SigmaShift       shift_video=12, shift_audio=3
→ 401 MiniMaxChunkFeedForward   chunks=2, seq_threshold=4096
→ 403 MiniMaxLowVRAMAttention   head_chunks=4
→ 329 ModelPreviewOverrideKJ    vae=36, tiny_vae=taeh3.safetensors, max_resolution=1024,
                                preview_fps=12, preview_frames=1024, jpeg_quality=80, suppress_default_preview=true
→ 397 SelfLiftH3Sampler.model（同时 329 → 261 BasicScheduler.model）
```

> 简写链 `343 → 403 → 329 → 397` 中间的 331/332/333/401 是注意力/移位/分块节点，不要漏接或改序：它们不调「武戏强度」，但改动会影响速度、显存与时序稳定性。

### 1.2 条件链

```text
38 CLIPLoader  qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors, type=minimax, device=default
36 VAELoader   minimax_h3_video_vae_int8_convrot.safetensors
37 VAELoader   minimax_h3_audio_vae_fp32.safetensors
51/49/50/43/19/23/199/200/201 LoadImage      → 265.ref_images.ref_image_0..8
27/25/26 VHS_LoadVideo                       → 265.ref_videos.ref_video_0..2
48/14/15 LoadAudio                           → 265.ref_audios.ref_audio_0..2
265 MiniMaxH3ReferenceToVideo  clip=38, vae=36, audio_vae=37,
    width=1344, height=768, length=124, ref_image_size=match, prompt=""
    ├─ out0 (positive) → 397.positive；同时 → 328 ConditioningZeroOut → 397.negative
    └─ out1 (latent)   → 397.latent_image
328 ConditioningZeroOut  即 negative 不是文本负面提示词，而是正条件清零得到的零条件。
```

字段绑定仍按上级 `bindings.yaml`：`ref_image_0..8 → 51/49/50/43/19/23/199/200/201.image`、`prompt → 263.text`、`duration_seconds → 259.value`、`aspect_ratio/megapixels → 252`、`filename_prefix → 364.filename_prefix`。
原样保留的游离节点（API 图中无下游引用，固化时不删不接）：`259 PrimitiveFloat(10) → 250 ComfyMathExpression(max(5,round(a*24))+…%17)`、`252 ResolutionSelector(16:9, 1.5MP, multiple=32)`、`263 Text`、`366 GoohaiUniversalSlider(值=3, int)`。实际生效的画面/时长参数以 265 的 `width/height/length` 为准，改 252/259 不要指望直接改变 265。

### 1.3 采样链

```text
255 KSamplerSelect   sampler_name=euler
261 BasicScheduler   model=329, scheduler=simple, steps=10, denoise=1
397 SelfLiftH3Sampler
    model=329, positive=265.out0, negative=328, latent_image=265.out1, vae=36,
    sampler=255, sigmas=261, seed=905138662823835, cfg=1,
    transition_step=6, lowres_scale=0.6,
    upscaler_model=minimax_h3_latent_upscaler_3d_fp16.safetensors,
    highres_tiling=false, upscaler_unload=true, rho=0, w_min=0.5, w_max=1
```

### 1.4 解码与输出链

```text
397.out0 → 253 VAEDecode(vae=36) ──────────────┐
397.out0 → 254 VAEDecodeAudio(vae=37) ─────────┤
                                               → 364 VHS_VideoCombine
    frame_rate=24, filename_prefix=YZ_H3_, format=video/h264-mp4, pix_fmt=yuv420p,
    crf=19, loop_count=0, pingpong=false, save_metadata=true, save_output=true, trim_to_audio=false
397.out0 → 9001 MiniMaxH3MotionContextSaveLatent
    filename_prefix=h3_context/wenwu_test, clip_index=1 → 9002 PreviewAny
```

## 2. 武戏参数表（当前固化值 + 作用 + 可调范围 + 预期效果）

下表「建议可调范围」是单变量调参的安全探索区间，不是已实测结论；每次只改一个、步长 0.05~0.1（速度滑杆 0.5），同 seed 对比。

| 节点 | LoRA / 参数 | 当前值 | 作用 | 建议可调范围 | 调高预期 | 调低预期 |
|---|---|---:|---|---:|---|---|
| 53 | `minimax_h3_dmad_full_dareties_v4_step600` | 0.8 | 基础生成质量/细节底座（非武戏专用，全片型共用） | 0.6–0.9，武戏一般不动 | 质感/细节更强，但可能与后续武戏 LoRA 抢权重、动作变僵 | 更听后续 LoRA 的话，但画质底座变弱 |
| 400 | `MysticXXX_MMH3-V1` | 0.35 | 画风/质感修饰（非武戏专用） | 0.2–0.5 | 风格化更重，可能压动作幅度 | 风格变淡，动作相对更突出 |
| 342 | `H3_Combat_V2` ★ | **0.65** | 武戏核心：打斗招式、攻防、命中感的主要来源 | 0.45–0.85 | 招式更明确、出招/受击更像打斗；过高易肢体扭曲、武器变形、多人缠斗粘连 | 动作变日常化、打斗变推搡；画面更稳 |
| 344 | `Motion_Repair_V2` ★ | **0.35** | 动作修复：补快速运动中的肢体/轮廓崩坏 | 0.2–0.6 | 断肢、融化、残影减少；过高会把动作「修平」、速度感变钝 | 动作更锋利但崩坏、拖影增多 |
| 345 | `H3_Fight_Flow_V1` ★ | **0.35** | 打斗连贯：招式衔接、攻防节奏、动作不中断 | 0.2–0.6 | 连招更连绵、攻防转换顺；过高易一镜黏到底、该停不停、节奏发飘 | 每招更独立分明；过低易动作一卡一卡、打斗断片 |
| 343 | `motion_speed_slider_mmh3_v1.1` ★ | **3.0** | 运动速度滑杆：整体动作速度/位移幅度（注意量纲与普通 LoRA 不同，3.0 是滑杆值不是 300%） | 1.0–5.0（先在 2.0–4.0 内试） | 动作更快、位移更大、打击感强；过高是快速武戏崩坏的头号原因（糊、残影、穿模） | 动作变慢变稳、像慢镜；过低打斗变「太极推手」没力度 |
| 397 | `transition_step` | 6（共 10 步） | SelfLift 低清→高清切换步（见 §3） | 5–7 | （值越大）低清阶段更久、高清修复步数更少，省时但快速动作细节修不回来 | （值越小）更早进高清，细节/稳定性好但更慢、更吃显存 |
| 397 | `lowres_scale` | 0.6 | SelfLift 第一阶段低清缩放比 | 0.5–0.75 | 低清阶段分辨率更高、构图动作更准，但速度优势变小 | 更快更省显存，但大幅位移更容易在低清阶段就糊掉、错位 |
| 397 | `cfg` | 1 | SelfLift 引导强度 | 固定 1，不建议动 | 本工作流 negative 是零条件（328），cfg>1 不是常规「加强提示词」，易出伪影 | — |

## 3. SelfLift 与快速运动的关系

SelfLift 是两阶段采样：先以 `lowres_scale=0.6` 的低清 latent 跑前段 sigma，到 `transition_step=6`（10 步中的第 6 步）用 `minimax_h3_latent_upscaler_3d_fp16.safetensors` 把 latent 上采样，再以高清跑完剩余步数。`highres_tiling=false` 表示高清阶段整幅处理（不分块，画质一致性好、显存更高），`upscaler_unload=true` 表示上采样后卸载 upscaler 省显存。

对武戏（快速、大位移运动）的含义：

- 低清阶段决定动作的「大形」：招式走向、人物位移、镜头运动都在此定型。低清下相邻帧位移占比更大，快速挥击/腾挪最容易在这里糊成残影、肢体错位；高清阶段只能在此大形上修细节，救不回已经错位的动作轨迹。
- 因此快速武戏出崩坏时，优先怀疑低清阶段承载不住运动量：先降 343 速度（减少位移量），再考虑把 `transition_step` 提前到 5（多给高清阶段 1 步修细节）或把 `lowres_scale` 提到 0.7（低清大形更准）；两者都更慢/更吃显存，只能二选一试。
- `transition_step` 也不要过早（如 3–4）：高清步数变多会显著变慢，且大形未定型时就进高清，可能把错误姿态「精修」得更牢固。
- 本变体保持原值 `transition_step=6 / lowres_scale=0.6 / highres_tiling=false`，与原模板一致。

## 4. 可选调参表（建议值，未写入 JSON）

每次只改一行，固定 seed=905138662823835 对比；改完不满意先回滚再试下一行，不要叠加。

| 场景 / 症状 | 先改 | 建议值（原值） | 再改（仍不行才动） | 代价 / 说明 |
|---|---|---:|---|---|
| 动作崩坏：断肢、融化、武器变形 | 343 speed ↓ | 2.0（3.0） | 344 Motion_Repair ↑ 0.45（0.35） | 速度感下降；仍崩再降 342 Combat 到 0.55 |
| 打斗不够狠、像推搡 | 342 Combat ↑ | 0.75（0.65） | 343 speed ↑ 3.5（3.0） | 肢体/武器变形风险上升，盯手和兵器 |
| 动作一卡一卡、连招断片 | 345 Fight_Flow ↑ | 0.45（0.35） | 343 speed ↓ 2.5（3.0） | 过高会黏连、该停不停 |
| 动作黏连、一镜飘到底没停顿 | 345 Fight_Flow ↓ | 0.25（0.35） | 在 prompt 里写清分招/停顿 | 节奏分明但可能变断片 |
| 太快太乱、看不清招式 | 343 speed ↓ | 2.0（3.0） | 397 transition_step → 5 | 变慢、显存/耗时上升 |
| 太慢、没力度像慢镜 | 343 speed ↑ | 4.0（3.0） | 342 Combat ↑ 0.7（0.65） | 残影/穿模风险显著上升 |
| 残影、拖影、高速糊 | 344 Motion_Repair ↑ | 0.45–0.5（0.35） | 397 lowres_scale → 0.7（0.6） | 动作可能变钝；耗时上升 |
| 人物脸/服装漂移（打斗中） | 342 Combat ↓ | 0.55（0.65） | 400 Mystic ↓ 0.25（0.35） | 打斗强度下降；先确认参考图绑定无误 |
| 高清阶段显存爆/极慢 | 397 lowres_scale ↓ | 0.5（0.6） | 不要开 `highres_tiling` 冒充省显存方案，先降速 343 | 低清大形更不准，快速动作更易糊 |

## 5. 武戏使用注意事项

1. **动作崩坏的调参顺序**：先查 prompt 与参考图（动作描述是否一镜到底塞了多套招式、参考图是否冲突）→ 降 343 速度 → 升 344 修复 → 降 342 Combat → 最后才动 SelfLift（`transition_step`/`lowres_scale`）。不要一上来同时拉高 Combat+speed+Flow，三者叠加是崩坏的最常见人为原因。
2. **一镜一事**：一条单元只写一套连贯攻防；换招式、换机位、换场地拆到下一条。多人缠斗、兵器接触帧是最易崩的画面，能拆则拆。
3. **速度滑杆量纲不同**：343 的 3.0 是 slider 值，不要按普通 LoRA 的 0–1 直觉去「微调到 0.9」；调它用 0.5 步长。
4. **cfg 与 negative 别动**：397 的 `cfg=1` + 328 零条件是本工作流的既定组合，不要为了「加强打斗」去加文本 negative 或拉高 cfg。
5. **seed 对比**：调参时固定 397 的 seed，只改一个参数同条对比；定版出片再换 seed。当前固化 seed=905138662823835。
6. **接力 latent**：9001 照常存 `h3_context/wenwu_test` 的 motion latent；是否接上一条仍按仓库既有连续性规则（同场景连续才接、换场/`independent`/上一条已分屏则断开），本变体不改变该规则。
7. **TEST 定位不变**：上级 README.txt 明确本模板族是 TEST-ONLY，生产仍是 `templates/yz_h3_ep_unit`；本变体不改变这一定位。

## 6. 校验结果（2026-10-19 执行）

方法：`python3` 解析原模板与变体两份 JSON，逐节点（`class_type` + 全部 `inputs`）深比较，并比对文件 SHA-256。

```text
src  templates/yz_h3_wenwu_test/workflow_api.json
dst  templates/yz_h3_wenwu_test/variants/wuxi/workflow_api.json（json 解析→深拷贝→写出）
src_nodes=46  dst_nodes=46
semantic_equal=True  per_node_diff=[]        # 逐节点参数 diff 为空
src_sha256=72876ef88df67b850d5ae983c8f144d4a0d5f203d8fcede19e618e8e10a48f37
dst_sha256=72876ef88df67b850d5ae983c8f144d4a0d5f203d8fcede19e618e8e10a48f37
武戏默认值核对: 342 Combat=0.65, 345 Fight_Flow=0.35, 343 speed=3.0, 344 Motion_Repair=0.35,
  400 MysticXXX=0.35, 53 dmad=0.8, 397 transition_step=6 / lowres_scale=0.6 / highres_tiling=false,
  261 steps=10（JSON 中浮点存为 0.6500000000000001 等二进制表示，数值等价）
结论: 两份 JSON 可解析、语义完全一致、SHA-256 一致；原模板未修改。
```
