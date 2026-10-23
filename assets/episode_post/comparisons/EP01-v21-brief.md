# EP01 v21: independent agent edit comparison

## 给下一位 agent 的任务

以同一 EP01 v21 的四个 U 定版素材为输入，按项目 skill 自主完成一版
完整后期：剪辑、英文短句字幕、配乐、结尾、QC 和实际成片审核。
在完成自己的首版计划前，不读取其他 agent 的 EDL/creative_plan 或成片。
不要复制某一版剪辑点来制造“独立制作”，也不为追求差异而无理由改动。

共享输入：`assets/episode_post/comparisons/EP01-v21/inputs.json`，由
`scripts/episode_post/prepare_episode_comparison.py` 锁定源文件、词轨、prompt、
元数据、skill、许可资产及 ending 库版本。检查文件 hash 一致再执行。

输入约束：
- 剧情顺序、必需台词和动作保持完整；不补生成、不改对白或人物事实。
- 英文语义短句字幕；768x1376/24fps、48kHz；整集约 -16LUFS、编码后
  true peak 不高于 -1.5dBTP。此为比较用技术约定，不是平台通用标准。
- 资产池目前只有 Undertow，可选不同段落、强弱与留白；不引入额外曲目，
  防止把素材资源差异误认为 agent 判断差异。
- 已认可 ending 可选，不强制所有版本相同；若另选方案，先适配并验证
  实现，记录引擎差异。当前比较 runner 已支持完整接入 bloom-hold-suspense v1。

## 保存结果

每个 agent 独立写新目录，例如 `outputs/episode-comparison/EP01-v21/agent-b/`。
保存输入契约/hash、渲染前决策计划、源入出点与理由、配乐/SFX时码与参数、
成片/字幕、QC、审核和实际输出 hash。记录执行代码的 hash，分清创作差异
与渲染实现差异。不得覆盖其他候选，也不擅自上传或发布。

公共渲染入口：
`python scripts/episode_post/run_episode_comparison.py <共享输入> <自己的计划> <新目录>`。
计划字段见 `scripts/episode_post/comparison-plan-format.md`；不要先读别人的具体计划。
新渲染能力仍限定 EP01、原生画幅和已支持方案，不声称完全通用。

比较时先隐藏 agent 名称，再看剧情清楚度、接缝/重复、字幕阅读、音乐留白、
结尾吸引力和整体自然程度；技术失败先单独列出，不用平均分掩盖缺句等阻断。
当前主 agent 已接触前序试片和本会话，且 skill 含历史例子，因此这不是严格
盲测或统计实验。另一个 agent 的独立首版可以帮助判断执行差异，但不能
单凭两条结果推断模型整体优劣。
