# 对白批量核对（双语）— wuxi 优化前 / 优化后

日期：2026-10-20。范围：EP17+EP18 共 32 条（两版各 16）。
方法：抽音轨 → faster-whisper 转写 → 与剧本 `（）` 台词自动比对。

怎么读这份报告（两种情况，先分清）：
- **真对白问题**：剧本有台词，片子说错、漏说、重复说——需要处理，
  只在下一节「有对白的 4 条」里。
- **工具误读（不是片子的问题）**：剧本无台词的条，音轨只有兽吼/呻吟/
  剑风/撞击。语音识别被迫转写时，会把这些非语音声音拼成英文词，
  脚本因此标红。**标红 ≠ 片子说了错台词，更 ≠ 人物乱开口**；
  这类条目集中在最后一节，只是留作证据，无需处理、不必开片。

## 有对白的 4 条（重点）

### EP17-U03（Liam 独白）
- 期望：Next.（下一个。）
- 优化前听到：Next. ✓
- 优化后听到：Next. ✓

### EP17-U07（Cain 拔剑咆哮）
- 期望：A beast is still a beast! I will take your head myself, gutter scum!
  （畜生终究是畜生！我要亲手砍下你的头，阴沟里的贱种！）
- 优化前听到：It's still a beast! I will take your head myself, gutter scum!
  （它终究是头畜生！我要亲手砍下你的头，阴沟里的贱种！）— 开头略缩，意思对 ✓
- 优化后听到：This is still a beast! I will take your head myself, gutter scum!
  （这终究是头畜生！我要亲手砍下你的头，阴沟里的贱种！）✓

### EP18-U03（Cain 拔剑失败惊恐）⚠️ 两版都重复了一遍
- 期望：Impossible! My sword is blessed by the High Templars!
  （不可能！我的剑受过至高圣殿骑士的祝福！）
- 两版听到：My sword is blessed by the high Templars! **Impossible!**
  My sword is blessed by the high Templars!
  （我的剑受过至高圣殿骑士的祝福！**不可能！**我的剑受过至高圣殿骑士的祝福！）
- 结论：台词本身说对了，但**整句说了两遍**（先蹦后半句、再整句重来）。
  自动比对按词覆盖算 PASS，这种「重复说」要靠看转写才发现。

### EP18-U08（Liam 质问血统）
- 期望：Lord Vane! Is this the best your bloodline has to offer?
  （范恩大人！这就是你们血脉能拿出的最好货色了吗？）
- 优化前听到：Lord Vayne, is this the best your bloodline has to offer? ✓
  （Vayne 是转写拼写差，不影响）
- 优化后听到：同上 ✓

## 无对白单元：工具误读留痕（不是台词错误，无需处理）

下面 12 条剧本都没有台词。表里的英文不是人物说的话，是 Whisper
把兽吼、呻吟、音效误听成的英文词，列出来只为证明「标红是工具误读」，
不是片子的问题。判断方法：中译读不通、或与画面声音（吼/呻吟/撞击）
对得上，即可排除。

| 单元 | 优化前误听为 | 优化后误听为 | 实际是什么声音 |
|---|---|---|---|
| EP17-U01 | Sanny Wangoyan fey khandram sent town | Sanny Wangloyan fakeongram sentown | 无意义音节（兽吼） |
| EP17-U04 | I aim. I variety. | High Aim. High Variety. | 无意义短句（音效） |
| EP17-U05 | Asked you to find me. | Asked to uniform it | 字面像人话，实为音效幻觉 |
| EP17-U06 | See you guys out tomorrow then. | See ya, yo. Have to! South Emolia! | 字面像送别语，实为幻觉 |
| EP18-U02 | One golem fey funder sin carer… | Our goliaths fitifunda… | 无意义音节（剑风/兽吼） |
| EP18-U05 | What we are? Police! | （无）✓ | 惊呼类幻觉；优化后干净 |
| EP18-U06 | UGH! I'm dead!（啊！我死了！） | Ugh! Ugh! Ugh!（呃！呃！呃！）✓ | 踩脸呻吟；优化后是纯呻吟、对 |
| EP18-U07 | Let's view them / That's few done | They're feud on… | 无意义（人声喧哗底噪） |
| 其余 | You / Oh 等单音节 | 同 | 不构成台词，PASS |

## 汇总

- 对白 4 条：内容两版全对；**EP18-U03 两版都重复说了一遍**，是唯一真问题。
- 无对白 12 条：优化前 8 条、优化后 6 条被工具误听出英文词，均为误读，
  不是台词错误；其中 EP18-U05、U06 优化后连误听都没有（纯音效/呻吟）。
- 锁嘴改动（U03/U08）在转写层面两版无差别——ASR 本就分不出谁在说；
  口型归属仍需看动态，本报告核的是「说了什么」。
