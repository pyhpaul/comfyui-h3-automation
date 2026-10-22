# 说话人归属审核 V2 与误判事故记录（2026-10-21）

## 1. 事故摘要

潮缚 fx21 的 39 条 Colab 成片完成词面审核后，用户人工观看发现
EP01-U06、EP02-U04 存在人物与对白错位。此后针对两条制作了结构改写、
换种子和断链候选，并曾依据 ASR 结果与稀疏静帧给出两个错误结论：

- `EP01-U06-seed2`：曾记为 STRICT，用户完整实看后确认第一句开口人物仍错；
- `EP02-U04-indep`：曾记为 STRICT，用户完整实看后确认人物对白仍错。

两条结论均已撤回，登记表槽位退回 `pending`，当前无合格修复候选。
错误候选没有覆盖飞牛 V3 正片；V3 中仍是原始问题版本。候选说明与
给资产方的建议已同步纠正。

这不是单个审核员漏看一帧，而是审核方法把“筛查证据”误用成了“定案证据”。

## 2. 为什么旧方法会误判

1. **ASR 只回答说了什么，不回答谁在说。** 串嘴时台词文字、顺序甚至时间戳
   都可以完全正确，因此词面 PASS 对说话人归属没有证明力。
2. **段中点帧和稀疏静帧不能证明动态口型归属。** 一张张口帧可能落在词间、
   反应动作或错误人物短暂张口处；只抽若干时间点，还会漏掉镜头内换人、
   听者同步动嘴和音画错位。
3. **登记工具没有强制保存人工审核证据。** 旧 `fix_registry.py` 允许只凭
   一个 verdict 字符串就把候选记为 STRICT 并把槽位标成 shipped。
4. **否决不能自动回退槽位。** 旧工具把候选改成 FAIL 后，槽位仍可能停在
   `shipped-strict`，造成登记表自相矛盾。
5. **人物身份只靠单帧印象。** 没先用参考设定和相邻单元锁定每个人的脸、
   服装与站位，就在候选帧上判断“这是谁”，身份基准本身不够稳。

## 3. V2 审核流程（强制）

### 3.1 自动筛查：只给线索，不给定案

每条候选仍先跑：

```bash
PYTHONPATH=src .worktrees/feat-orch/.venv/bin/python \
  scripts/ops/audit_candidate.py <UNIT> <候选目录>
```

输出的 `candidate_audit.json` 固定带：

- `decision: "NOT_DECIDED"`
- `automated_checks_only: true`
- `review_status: "REQUIRED_NOT_DONE"`（或已存在的审核进度）
- `human_review.json` 清单路径

ASR、逐词时间戳、F0/RMS、镜头切分点和亮度只用于定位问题与安排人工
审核。禁止把这些结果写成“说话人正确”“口型通过”或候选 PASS。

`audit_candidate.py` 会按每 0.25 秒为每个对白段生成密集静帧，放在
`frames/review_seg<N>/`。这些帧只用于快速定位要看的时刻，仍不是定案
证据；审核员必须回到原视频连续观看。

### 3.2 先锁定人物身份，再看对白

逐句审核前，先从本条 `prompt_source.txt` 的参考设定及相邻已确认单元
建立人物表：姓名、脸部特征、发型、服装、站位。候选里人物换装、戴面罩、
侧脸或背对镜头时，必须在审核记录中写明身份依据；身份无法确认的对白段
记为 `UNVERIFIABLE`，不得记 STRICT。

### 3.3 完整观看每个对白段

对剧本的**每一句**对白（不是抽查其中几句）执行：

1. 从该句第一个词前至少 0.5 秒开始，连续看到最后一个词后至少 0.5 秒，
   带声音观看，不静音、不跳帧。
2. 记录点名说话人、实际持续动嘴的人、同框其他可见嘴部是否全程闭合。
3. 核对台词完整、顺序正确、没有被另一人抢说或两人同念。
4. 说话人正脸不可见、嘴被遮挡或只能看到听者时，不能凭声音猜归属；
   该句记为不可验，候选不得 STRICT。
5. 双人及以上同框、快速正反打、画外音接正脸、接力缝第一句，全部视为
   高风险段，必须完整观看；不允许用段中点帧代替。

`human_review.json` 中每句最初均为 `UNREVIEWED`。审核员逐句填写
`expected_speaker`、`mouth_owner`、`other_visible_mouths`、
`line_complete`、`line_order` 后，才可进入登记定案。

### 3.4 登记表证据门

`fix_registry.py` 现在拒绝无完整人工审核记录的通过判定。STRICT 或
RELAXED 必须同时提供：

- `--review-method full-dialogue-watch`
- `--review-scope all-dialogue-lines`
- `--reviewer <姓名>`
- `--review-evidence <逐句实看依据>`

示例：

```bash
python scripts/ops/fix_registry.py --registry runs/<本轮>.json verdict \
  --unit EP01-U06 --chain wenxi --tag seed2 --verdict strict \
  --review-method full-dialogue-watch \
  --review-scope all-dialogue-lines \
  --reviewer lai \
  --review-evidence "完整观看三句：L1 Cole 动嘴、Wade 闭嘴；L2 ...；L3 ..."
```

没有完整实看记录时，工具直接拒绝，不改登记表。后续实看否决时可直接
再记 FAIL；槽位会按剩余候选自动重算，没有其他通过候选时退回
`pending`。禁止手工改 JSON 绕过证据门，也禁止只改槽位不改候选判定。

### 3.5 出版前复核

覆盖正片或放入修复定版前，再核对四件事：

1. 登记表中候选 verdict 与人工结论一致；
2. `review` 的审核人、范围、方法和逐句依据齐全；
3. `human_review.json` 没有 `UNREVIEWED` 或 `UNVERIFIABLE` 句；
4. 飞牛候选说明与登记表一致。

任何一项缺失，状态只能是待审，不得说“修复成功”。

## 4. 判定用语

- **自动筛查完成**：只表示 ASR/时间戳/切分点已生成，未审核说话人。
- **待完整实看**：`human_review.json` 尚未逐句完成。
- **候选通过**：完整实看逐句通过，且登记表已有强制审核记录。
- **修复成功**：候选通过并已按规定覆盖或进入定版目录，归档复核齐全。

禁止用“帧审通过”代替“完整实看通过”；禁止把词面 PASS、密集静帧或
F0 结果单独写成候选通过依据。

## 5. 本次工具修复

| 工具 | 修复内容 |
|---|---|
| `scripts/ops/audit_candidate.py` | 输出固定 `NOT_DECIDED`；新增 `human_review.json`；每段生成 0.25 秒间隔导航帧；重跑不覆盖已有审核清单 |
| `scripts/ops/fix_registry.py` | STRICT/RELAXED 强制完整实看证据；保存 reviewer/method/scope/evidence/time；FAIL 后自动重算槽位 |
| `tests/test_fix_registry_review_gate.py` | 回归测试：无证据通过被拒、有证据通过可登记、FAIL 回退 pending、审核清单初始不可定案 |

## 6. 对本轮两条的现行结论

- EP01-U06：所有已审候选均为 FAIL，无合格修复版。
- EP02-U04：所有已审候选均为 FAIL，无合格修复版。
- 后续重修必须按 V2 逐句完整实看；在重新定案前，不得沿用本轮任何
  “赢家”“STRICT”或“断链已解决”的旧说法。
