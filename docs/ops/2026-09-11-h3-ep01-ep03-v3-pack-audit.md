# 审核：H3-EP01-EP03-调用包-v3

**日期：** 2026-09-11  
**包路径：** `C:\Users\lxy\Downloads\H3-EP01-EP03-调用包-v3.zip`  
**解压：** `/mnt/c/Users/lxy/Downloads/H3-EP01-EP03-调用包-v3/`（及 `/tmp/h3_ep01_ep03_v3/…`）

## 结论（先看）

| 项 | 结果 |
|----|------|
| 包内素材完整性 | **通过**（TXT 中「文件存在」的包内路径均能找到 PNG） |
| 与旧包格式 | **不兼容**：新格式 = `manifest.csv` + 共享 `assets/<id>/` + `EPxx/epxx-syy-cz.txt` |
| 当前 `ep_pack_to_jobs` | **不能直接吃**（缺 `upload-manifest.json` / causality `manifest.json` / latent 布局） |
| 提示词可编排性 | EP01/EP02 **部分可适配**（有「仅复制进 H3」+ `@图片N`）；**EP03 全部失败**（复制区为空） |
| YZ `ref_image_0..5` 槽位 | **7 个 U 溢出**（≥7 张可上传静图） |
| 控制图 | **多数待生成**（28/32 U），不可当作 `ref_image_0` |
| 续跑 latent | 包内仅 **planned** 链路说明，**无真实 latent/成片** |

**总评：** 这是「给老板手动在 H3 网页点」的静态调用包，不是现有编排器的 job 源。要进 `yz_h3_ep_unit` 需要新 pack kind + 标签改写（`@图片N`→`<Picture N>`）+ 控制图/溢出槽策略；**EP03 须先补齐模型输入文本**。

---

## 1. 包结构（拆解）

```text
H3-EP01-EP03-调用包-v3/
  README.md
  manifest.csv                 # 32 行 U 索引（Episode,U,Seconds,File,AssetCount,ControlState）
  assets/<asset-id>/*.png      # 共享素材库（43 个目录）
  EP01/ep01-s{01..04}-c*.txt   # 11 U
  EP02/ep02-s{01..03}-c*.txt   # 11 U
  EP03/ep03-s{01..03}-c*.txt   # 10 U
```

每个 TXT 固定块：

1. 元数据（时长、来源路径）
2. **上传顺序与路径**（含「文件存在 / 待生成」）
3. **H3 链路与剧情**（latent_in/out=planned）
4. **仅复制进 H3 的模型输入文本**（EP01/EP02 有正文；EP03 空）

编号是 **场-镜**（`s01-c1`），不是旧 causality 的 `U01`。

---

## 2. 与之前资产包的差异

| 维度 | 旧 EP02 causality v2.1 | 旧 EP01 latent / EP03 upload | **本包 v3** |
|------|------------------------|------------------------------|-------------|
| 清单 | `manifest.json` | `upload-manifest.json` / 目录约定 | **`manifest.csv`** |
| 单元 ID | `U01`… | `U01`… | **`ep01-s01-c1`…** |
| 提示词形态 | 中文因果段 + 路径列表；wire→`<Picture N>` | latent 包 / Seedance→六段英文 | **`@图片N` 中文 H3 文案**（无 `<Picture>`/`<Video>`） |
| 素材布局 | `assets/{characters,props,scenes}/` | 按 U 或 control/previz | **`assets/<包内资产号>/`**（号≠原文件名） |
| 控制图 / previz | 测试包可不强制 | Seedance 常有 control+previz | **控制图大多「待生成」；无 previz 视频** |
| 连续性 | 强调父 AV latent + 末 1s 重叠 | 各异 | **planned latent 链**；README 要求父→子 blocked |
| 范围 | EP02 物理因果子集（~7U） | 单 EP 试验 | **EP01–EP03 全 32U 手动调用** |
| 用途声明 | 测试因果 | 编排试跑 | **明确：未上传、未提交；H3 字段未实测** |

素材内容：与 causality 测试包 **PNG 文件名有交集**（如 `char-001.png`、`char-003-v5.png`、`prop-013-…`、`scene-007.png` 等），但 v3 另有大量新变体（`char-001-v2/v3`、`scene-008-a2`、闸门/矛等）。**剧情/分镜粒度不同**：v3 是正式场次链，不是同一套 U01–U07 因果测试文案。

---

## 3. 当前工作流能否适配

### 3.1 直接跑（现状）

```text
python scripts/ep_pack_to_jobs.py <本包根> …
→ ValidationError: missing upload-manifest.json
```

`causality_pack` / `latent_pack` 同样认不出 `manifest.csv`。

### 3.2 若加适配器，理论路径

1. 解析 `manifest.csv` + 各 TXT「文件存在」行 → 静图列表（**跳过待生成控制图**）。
2. 取「仅复制进 H3」正文；`@图片N` → `<Picture N>`（wire-only，禁止六段改写）。
3. 槽位：无 control 时顺序填 `ref_image_0..5`（最多 **6** 张）。
4. 子镜：`--continuity motion_latent`（与包内 planned 链一致）或临时用上一条 MP4 做 `ref_video`（包未提供父片）。
5. `duration_seconds` 取 TXT「时长」（**6–12s 不等**，勿写死 10）。

### 3.3 阻塞项（审核未通过）

1. **EP03 全部 10 个 U**：`## 仅复制进 H3 的模型输入文本` **为空**；上方只有短叙事，**无 `@图片N` 映射句**。不能按 wire-only 安全出片。
2. **槽位溢出**（可上传静图 >6）：  
   `ep02-s03-c1/c2/c3`，`ep03-s03-c1..c4`（最多 **9** 张）。现模板只有 `ref_image_0..5`。
3. **提示词仍引用待生成控制图**：EP01/EP02 的 `@图片K` 常多占 1 个 ctrl 槽；若不上传 ctrl，须删改对应 `@图片` 句，否则标签悬空（违反「只换标签、不改语义」时要单独政策）。
4. **资产号漂移**：如 `assets/char-005/char-010-nurse.png`、`scene-005/scene-007.png`。必须以 TXT **包内路径**为准，不能按文件夹号猜原项目 `char-010`。
5. **无控制图 / 无 previz**：与旧 Seedance upload 路径不同；YZ「控制图」槽只能改用身份图顶上或留空（需产品决定）。
6. **README 约束**：父 latent 未验证则子条 blocked；当前编排若强行 `ref_video` 串 MP4，与包设计的 latent 链不一致（应用 `motion_latent`，且仍缺真实句柄）。

---

## 4. 逐 EP 审核摘要

| EP | U 数 | 模型输入区 | 控制图待生成 | YZ 槽位 | 建议 |
|----|------|------------|--------------|---------|------|
| EP01 | 11 | 齐全，`@图片` 完整 | 9/11 | 均 ≤6 可上传图 | 适配器落地后可试跑（先跳过 ctrl 并处理 `@图片` 悬空） |
| EP02 | 11 | 齐全 | 9/11 | s03 三镜 **溢出 +1** | s01/s02 可试；s03 需减槽或扩模板 |
| EP03 | 10 | **全空** | 10/10 | s03 四镜溢出 +1…+3 | **打回补文案后再谈编排** |

`manifest.csv` 的 `AssetCount` 含控制图占位，故会大于「文件存在」静图数（例如 `ep02-s02-c1`：uploadable=5，AssetCount=7）——属清单口径差异，不是缺文件。

---

## 5. 门禁清单（本包）

- [x] Zip 可解压；README / CSV / 三 EP TXT / assets 齐全  
- [x] 「文件存在」→ 包内 PNG **0 missing**  
- [ ] 可被现有 `ep_pack` kind 识别 — **否**  
- [ ] EP03 模型输入可提交 — **否**  
- [ ] 全 U 静图 ≤6 — **否**（7 U 溢出）  
- [ ] 控制图可上传 — **否**（多数待生成）  
- [ ] 父 latent 句柄可用 — **否**（仅 planned）  

---

## 6. 建议下一步（需你拍板后再改代码）

1. **EP03**：让分镜包补「仅复制进 H3」+ `@图片N` 映射（与 EP01/EP02 同结构）。  
2. **产品**：溢出 U 是「砍道具参考」还是「扩 YZ 槽 / 拆 U」？待生成 ctrl 是「删 `@图片` 控制句」还是「等控制图」？  
3. **工程**：新增 pack kind（如 `h3_manual_csv`）+ `@图片`→`<Picture>` wire + 审计脚本扩展。  
4. **出片模式**：确认 `motion_latent` vs `ref_video`（见 render-mode gate）；本包语义偏向 latent 链。

未实现适配器前，**不要**对 v3 跑 `run_ep_units_profiled` / `comfy-orch submit`。
