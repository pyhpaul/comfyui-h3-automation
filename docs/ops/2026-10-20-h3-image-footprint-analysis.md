# H3 镜像占用分析：初版 / 新版文武 / 两版并存（2026-10-20）

背景：当前晨羽镜像约 80 GiB。本文按两个工作流实际引用的模型文件
（逐个核字节，来源 `/mnt/d/comfyui/models` 博主原始目录 +
`models.tar` 旧快照清单）算三种配置的净占用，并列当前镜像的冗余候选。

## 两版共用底座（谁都跑不了）

| 文件 | GiB |
|---|---|
| `minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors`（UNET） | 19.53 |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`（CLIP） | 14.61 |
| `minimax_h3_video_vae_int8_convrot.safetensors` | 2.95 |
| `minimax_h3_audio_vae_fp32.safetensors` | 0.56 |
| `MysticXXX_MMH3-V1.safetensors` | 0.56 |
| **共用小计** | **38.21** |

## 三种配置

| 配置 | 独有文件 | 模型总计 |
|---|---|---|
| 只有初版 `yz_h3_ep_unit` | turbo LoRA 0.58 | **38.79 GiB**（与 G4 恢复记录的六模型 38.79 GiB 一致） |
| 只有新版文武 `yz_h3_wenwu_test`（含 wenxi/wuxi 两 variant） | dmad 0.89 + latent_upscaler_3d_fp16 0.64 + H3_Combat_V2 / H3_Fight_Flow_V1 / Motion_Repair_V2 各 0.14 + taeh3 0.01 + motion_speed_slider 0.0002（187,384 B）= 1.98 | **40.19 GiB** |
| 两版放一起 | 共用一份 + turbo 0.58 + 新版独有 1.98 | **40.77 GiB** |

结论：

- 新版只比初版多约 1.4 GiB；两版并存只比单新版多 0.58 GiB。
- 文/武 variant 引用同一套文件（文戏只是强度改 0，LoRA 文件仍须在盘），
  「文武一起」不增加占用。

## 运行环境（非模型）

来自 `runtime.tar` 实测：`.venv` 8.33 GiB，ComfyUI 源码 + custom_nodes
约 0.5 GiB。即「两版一起」的合理镜像 ≈ 40.8 + 8.9 ≈ **50 GiB**
（另加系统基础部分），当前 80 GiB 中约 30 GiB 为冗余。

## 冗余候选

已确认在旧快照 `models.tar` 里、两版工作流均未引用（可删，约 5.0 GiB）：

- `minimax_h3_video_vae_fp16.safetensors` 4.85 GiB（两版 VAELoader 均指 int8 版）
- `wushu_spatial_physics_v2_1000_pruned.safetensors` 0.14 GiB

博主原始目录里有、疑似被带进租卡镜像（需开机 `du` 确认）：

- 旧 UNET `minimax_h3_hybrid_fl2va_ref2va_b20-49-int8.safetensors` 19.53 GiB
- 备用 CLIP `qwen3vl_32b_minimax_h3_ultra_uncensored_heretic_int8_convrot.safetensors` 24.55 GiB
- 未引用的 upscaler 变体 ×3（sharpness fp32 1.29 + 3d_conv_v1 0.64 + lms v0.1 0.64）2.57 GiB

其他嫌疑：`/root/ComfyUI` 与 `/root/autodl-tmp/ComfyUI` 双份 ComfyUI、
`input/` 历史上传残留、pip 缓存。

## 待办

开机后跑一次 `du -sh /root/* /root/autodl-tmp/ComfyUI/models/*` 按本表核对，
确认冗余清单后再谈删/重做精简镜像。本文数字为本地文件实测，
租卡盘上实际构成以那次 `du` 为准。
