# Episode post-production assets and pilot tools

项目正式持有的后期代码。旧研究 worktree 不再是执行依赖或维护入口。
当前实现仍是 EP01 v21 的有界试片，不宣称已实现任意 EP、语言、尺寸或
多曲自动编排。已认可 ending 资产见 `assets/episode_post/`，选用规范见
`docs/ending-presets/index.md`。

## 环境

Python 3.11+、FFmpeg/ffprobe（含 libx264、libass、drawtext），以及
DejaVu Sans / Serif 字体。Python 库记录为本次验证版本；在项目环境安装：

```bash
python3 -m pip install -e '.[dev]' -r scripts/episode_post/requirements.txt
python3 -m pytest -q tests/test_ep_pilot.py tests/test_ep_pilot_music.py \
  tests/test_ep_pilot_audio_qc.py tests/test_ep_pilot_creative.py tests/test_episode_post_assets.py
python3 scripts/episode_post/verify_project_assets.py
```

Whisper small 转写要求模型已在本机缓存；转写脚本使用 `local_files_only=True`，
不会为归档自动联网下载模型。依赖安装、模型恢复与运行分开处理。

## 入口

- `prepare_ep_post_pilot.py` / `prepare_ep_post_v3.py` / `prepare_ep_post_v4.py`：
  生成版本锁定的 EP01 输入，原文件存在时拒绝覆盖。
- `run_ep_post_pilot.py <manifest> <新目录>`：母版、英文审片版、字幕和 QC。
- `transcribe_ep_pilot.py <视频> <分析目录>`：新 ASR 与源 hash。
- `verify_ep_post_pilot.py <输出目录>`：实际成片身份、台词、音频锚点及画面扫描。
- `preview_ep_bloom_ending.py <项目根>`：以 EP01 与已有 v4 渲染工作件做泛光概念。
- `hold_ep_ending_preview.py <项目根>`：从项目私有基底样片生成新增一秒定格。
- `add_ep_suspense_sfx.py <项目根>`：生成该定格预览的本地合成悬疑音效版本。

这些是固定试片的审计/复现入口，目录或源 hash 不符时停止，不悄悄选别的素材。
库中 JSON 是方案参数档案，尚不是通用自动渲染配置。

## 媒体归属与重放

- 公开认可样片：`assets/episode_post/endings/bloom-hold-suspense/v1/preview.mp4`。
- 私有素材：`assets/episode_post/local/`，由项目本地持有并由 Git 忽略，
  不随公开仓库分发；不是研究 worktree 所有。
- 私有完整试片输入约定：`local/pilots/lihun-v21-ep01/units/`、`analysis/`、
  `music/`。原素材/模型不在公开仓库，缺少时按 hash 从项目媒体备份恢复，
  不能声称单靠 clone 可重建整集。
- 私有 5 秒基底：`local/endings/bloom-hold-suspense/v1/base-bloom.mp4`，
  SHA256 在项目资产清单中。存在时可重放后两步；输出已存在则拒绝覆盖。
- `.cache/ep_post_pilot_v*/` 仅保存生成的任务输入；`outputs/ep-post-pilot/`
  仅保存运行产物，不再充当已认可样片的唯一保管位置。

本次归档不改变已认可 MP4 的字节，不自动发布新 EP，不合并主分支。
