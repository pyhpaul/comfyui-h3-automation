# 本地编排 + 远程 ComfyUI（MiniMax H3）自动化框架设计

**日期：** 2026-09-08  
**状态：** 已批准  
**范围：** 第一期框架（不含租卡开关机、不含具体视频工作流节点图）

## 背景与目标

团队通过网上租 GPU 常驻实例部署 ComfyUI，并加载 **MiniMax H3 开源权重**（非 Moonshot Kimi；非 MiniMax 云端 API 节点计费路径）做视频生成。本地持续产出人物图、场景、提示词等资产后，需要一套自动化框架：

1. 将资产与任务配置接入远端 ComfyUI  
2. 按模板注入节点参数并提交运行  
3. 成片完成后拉取到本地指定目录  

**第一期成功标准：**

- 齐备的 job 目录经 CLI 提交后，能在配置的本地目录拿到成片  
- 缺资产或 Base URL 不通时尽早失败，原因可读，避免长时间空烧 GPU  
- 更换工作流只需新增模板包，不改 Runner / Client 核心代码  

## 决策摘要

| 议题 | 决定 |
|------|------|
| 模型 | MiniMax H3 开源权重，租卡上本地推理 |
| 实例形态 | 常驻 Pod/实例；人用网页开机 |
| 框架边界 | 本地编排 + 远程执行器（含完整性门禁）；**不做**开关机/自动隧道 |
| 任务入口 | CLI 优先；同一 Job 核心，目录监控（inbox）后置 |
| 连通性 | 只认 `COMFY_BASE_URL`（SSH 隧道或平台代理均可） |
| 参数注入 | 外部 `bindings.yaml`，优先按节点 Title，可回退节点 ID |
| 架构形态 | 精简自研（不绑 ComfyKit 等执行 SDK；不上一期队列/DB） |
| 生成模式 | 不在本期设计；由固定工作流模板 + 显式 bindings 承载 |
| 调通环境 | 无 GPU（或弱 GPU）VM 上跑**真 ComfyUI**，用于调工作流与导出 API JSON；**不在此环境跑 H3**。真推理只在租卡 |

## 双环境：VM 调通 → 租卡出片

为提高性价比，开发与出片拆开；框架只认 `COMFY_BASE_URL`，切换环境不改业务代码。

| | VM（调流程） | 租卡（出片） |
|--|--------------|--------------|
| ComfyUI | **真实例**（可无独立显存 / 不加载 H3） | 真实例 + H3 权重 |
| 用途 | 搭节点、定 Title、导出 `workflow_api.json`、对齐 bindings | 实际推理与成片拉取 |
| 是否跑 H3 | **否**（避免显存与费用） | **是** |
| 框架 | `COMFY_BASE_URL` 指向 VM；可用短链路/空跑或非 H3 小图验证 API 连通 | `COMFY_BASE_URL` 指向租卡（常经 SSH 隧道等） |

**应对齐：** ComfyUI 大版本、工作流 API JSON、节点 Title、自定义节点集合、模型**文件名**与目录约定（租卡上再放齐真实权重文件）。

**可以不同：** 有无 GPU、是否加载 H3、是否每次完整出片。

**与测试 mock 的关系：** 自动化测试仍可用假 HTTP ComfyUI（见「测试」）；VM 上的真 ComfyUI 是给人调模板用的，二者不互相替代。

## 架构总览

```
本地:  CLI → Job Runner → Manifest 门禁 / Binder / Comfy Client
                              │
                              ▼  COMFY_BASE_URL
远端:  ComfyUI (--listen) + H3 权重 + 模板工作流
       /upload · /prompt · /ws|/history · /view
```

**本期不做：** 网页/API 开关机、框架内建 SSH、inbox watcher、T2V/I2V/R2V 具体图、资产生成业务逻辑。

## 组件

| 组件 | 职责 | 非职责 |
|------|------|--------|
| CLI | `doctor`、`submit <job-dir>`、`status <job-id>`；可选显式 `retry` | 解析工作流图细节 |
| Job Runner | 状态机与本地状态落盘 | 直接拼 HTTP |
| Manifest | 读 `job.yaml`，按模板 schema 做完整性校验 | 知道 Comfy 节点 ID |
| Binder | `workflow_api.json` + `bindings.yaml` 注入；处理需上传的媒体字段 | 网络 I/O |
| Comfy Client | system_stats、upload、queue_prompt、等待完成、view 下载 | 业务字段语义 |
| Artifact Store | 成片落到 `outputs/<job-id>/`，保留 prompt_id 等元数据 | 二次剪辑 |

### 模板包布局

```
templates/<name>/
  workflow_api.json       # ComfyUI「Save (API Format)」
  bindings.yaml           # job 字段 → 节点 Title（或 ID）+ input 名；媒体标记
  manifest.schema.yaml    # 该模板必填字段与文件
```

## 数据流（`submit`）

1. 读 `job-dir/job.yaml`  
2. 按对应模板的 `manifest.schema` 校验；失败则不碰远端  
3. `GET {BASE}/system_stats` 连通检查；失败则提示检查实例/隧道  
4. 对 bindings 中标记为需上传的媒体字段：优先走 ComfyUI 已有上传接口（如图片 `POST /upload/image`），记录远端文件名；若模板需要视频/音频等而当前实例无对应上传 API，则约定文件已预置在远端 `input/`（人工或 scp），bindings 只写入文件名，框架不在本期扩展自定义上传协议  
5. Binder 深拷贝 API JSON 并写入文本/数值/远端文件名  
6. `POST /prompt` → `prompt_id`（job-id 由 Runner 生成，与 prompt_id 一并写入状态）  
7. 等待：优先 WebSocket `/ws`；断线则轮询 `/history/{prompt_id}`  
8. 解析 outputs，`GET /view` 下载到配置的本地输出根目录下 `outputs/<job-id>/`  
9. 写工作区 `runs/<job-id>/status.json` 为 done（或 failed）及成片路径

### Job 交接约定

```
job-dir/
  job.yaml      # template + 字段（含相对资产路径）
  assets/       # 人物/场景等文件
```

资产生成器只要按此约定产出即可，生成算法不在本框架内。

## 错误处理

| 阶段 | 策略 |
|------|------|
| validating | 不重试；改 job 后重新 submit |
| connecting | 不自动重试；依赖人工恢复连通 |
| uploading | 单文件有限次重试（如 3 次） |
| queuing（node_errors） | 不重试；属模板/bindings 问题 |
| running 失败 | 默认不自动重跑；提供显式 retry |
| collecting | 可重试下载（远端已完成） |

- 同一 `COMFY_BASE_URL` 第一期 **串行** 一个 running job  
- 可选 `POST /interrupt` → 本地 cancelled  
- 进程中断后可用已存 `prompt_id` 向 `/history` 对账并尝试续拉成片  

## 测试（轻量）

- **少量单元测试：** manifest 缺文件失败；bindings 写入夹具 JSON 正确  
- **一条 mock 集成：** 假 ComfyUI 跑通 upload → prompt → history → view → 落盘  
- **真机：** 人工 `doctor` + 短任务冒烟；不强制进默认 CI  

## 配置与运维假设

- **调通 VM：** 已安装与租卡对齐大版本的真 ComfyUI；可不配 GPU、不装 H3；用于编辑工作流并导出 API Format JSON  
- **出片租卡：** 已安装匹配版本的 ComfyUI 及 H3 模型文件（如 Comfy-Org/MiniMax-H3 重打包权重）；人用平台网页启动实例  
- 本机能访问当前目标的 `COMFY_BASE_URL`（VM 局域网/本机端口，或租卡经 SSH 隧道 / 平台 HTTP 代理等）  
- ComfyUI 默认无鉴权；公网裸暴露需自备防护（本期框架不实现鉴权网关）  

## 后续演进（非本期）

- inbox 目录监控（复用同一 Job Runner）  
- 租卡生命周期 / 自动隧道适配层  
- 多 Base URL 或真并发队列  
- 将 Comfy Client 替换为第三方 SDK（若有收益）  

## 参考

- ComfyUI Server Routes：`/upload`、`/prompt`、`/history`、`/view`、`/ws`  
- 权重：Hugging Face `Comfy-Org/MiniMax-H3`  
- 官方 API 示例：按节点修改 `inputs` 后提交 prompt  
- 社区参数化：按 Title 设参（如 comfy_api_simplified）、ComfyKit 标题 DSL（本期不绑定，仅作对照）
