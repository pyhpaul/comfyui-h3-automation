# EP 后期与 ending 方案项目归档

## 范围与保管位置

- Skill：`.cursor/skills/comfy-h3-episode-assembly/`。
- 正式代码与依赖说明：`scripts/episode_post/`，不再以研究 worktree 为入口。
- 回归：`tests/test_ep_pilot*.py`、`tests/test_episode_post_assets.py`。
- 可扩展 ending 库：`docs/ending-presets/`。
- 公开认可样片、许可、审核：`assets/episode_post/endings/bloom-hold-suspense/v1/`。
- 公私资产身份清单：`assets/episode_post/manifest.json`。
- 原剧集、原曲、词轨、5 秒基底：项目 `assets/episode_post/local/`，被 Git
  忽略。本机已经保管，不能因旧研究 worktree 被清理而丢失所有权。

用户明确批准将认可的 6 秒样片随公开 Git 仓库入库。除该样片外，不公开
原始剧集、参考录屏、模型、任务缓存、NAS 配置或完整配乐源文件。
公开 MP4 为2,511,580 bytes，SHA256：
`e9dc2f9868a8ead86986bacb1b11a014dee6c3371009a9831588e1b442660e55`。

## 核验

从最新 `origin/main`（`4a32066`）建立干净归档分支，未带入原工作目录的
无关未提交文件或其他功能历史。

- 40 项本功能回归通过，包含真实 FFmpeg 推近、尾卡像素、混音时间窗、
  源身份与公开资产 hash 检查；独立 reviewer 亦复跑40项通过。
- 公共资产校验通过；加 `--include-local` 后7项资产身份均通过。
- 在干净 worktree 从项目保管的私有基底重放定格和音效，生成 MP4 与
  认可公开样片 SHA256 完全一致。未改认可文件字节。
- 源码编译、skill 格式、staged diff 空白检查通过。
- 创建独立项目 venv，仅按 `.[dev]` 安装即可收集/执行新增回归；为此在
  dev 依赖明确加入已验证 NumPy。ASR 环境与模型仍按正式 README 单独准备。

全量测试并非全绿：394 passed、15 skipped、16 failed。16项均涉及缺失的
旧 `/tmp` 素材包或 `jobs/ep_units` 本地产物；在未修改的 `origin/main`
独立 worktree 对同一组文件复跑，原样得到同16项失败（另8项通过）。
本次没有删除/跳过/修改这些测试，也不扩大范围补造旧素材来制造绿灯。

## 能力与后续边界

`bloom-hold-suspense` v1 为用户认可的可选概念：泛光柔焦、峰值多定格1秒、
悬疑气流及低频重音、干净尾卡。不设为所有 EP 的默认方案，后续追加独立
方案或新版本，不覆盖已认可版本。

当前正式代码仍限定 EP01 试片，不能把其归档解释为任意 EP、多语、
自动多曲选配或完整 EP 已整合该 ending。私有源片缺失时，公开 clone
能查看与校验认可样片、跑无私有素材回归，但不能单凭公开文件重建整集。
完整 EP 整合、平台交付和发布批准另行处理；本次仅提交分支与 PR，不合并。
