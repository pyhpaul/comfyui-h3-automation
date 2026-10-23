"""Emit dialogue-check artifacts for the 2026-10-21 chaofu redo renders.

Per unit (in .cache/chaofu_fix1_verify/<U>/wenxi/):
  - <mp4stem>.srt        segment track (from batch_dialogue_check, /tmp root)
  - <mp4stem>_words.srt  word-level track (from candidate_audit.json words)
  - dialogue_check.md    per-unit bilingual verdict sheet
Plus nothing else; the combined bilingual report is written separately.
Verdicts/notes below were fixed by hand from the ASR + word tracks
(2026-10-21); the bag-of-words verdicts alone are NOT trusted here.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / ".cache" / "chaofu_fix1_verify"
TMP_VIDEOS = Path("/tmp/chaofu_redo_videos")
REPORT = ROOT / "runs" / "dialogue_check_chaofu_redo_1021.json"

UNITS = ([f"EP24-U0{i}" for i in range(1, 7)]
         + [f"EP62-U0{i}" for i in range(1, 8)]
         + [f"EP63-U0{i}" for i in range(1, 7)])

ZH = {
    "She's an outsider. We grew up together. We're family.":
        "她是外人。我们是一起长大的，我们是一家人。",
    "Family? Was I family when you cut my line? Or for five thousand?":
        "一家人？你剪断我绳子的时候，我算一家人吗？还是为了那五千块？",
    "Why keep digging up the past? Let's talk future.":
        "干嘛老翻旧账？谈谈以后吧。",
    "Old debts aren't settled. Why trust you with a new one?":
        "旧债还没清，凭什么信你再接新债？",
    "How much is left down there? That crate isn't all, right?":
        "下面还剩多少？不止那一箱吧？",
    "We've talked this long. You finally asked what you came for. "
    "So which is it? The treasure down there, or me? "
    "You know the answer better than anyone.":
        "聊了这么久，你总算问到正题了。到底图哪样？下面的宝贝，还是我？"
        "你比谁都清楚答案。",
    "Go home, Wade. Today's crate is nothing. The real prize hasn't surfaced.":
        "回家吧，Wade。今天这一箱不算什么。真正的大货还没露面。",
    "Keep following.": "跟紧。",
    "Mr. Harlow, if we keep chasing, something's going to happen.":
        "Harlow 先生，再追下去要出事的。",
    "If he can get through, why can't we?": "他能过去，我们为什么不能？",
    "Our boat's wider than theirs.": "我们的船比他们的宽。",
    "The spot's right ahead. I'm getting it today.":
        "点位就在前面。今天我必须拿到。",
    "Uncle Victor, you can still turn back. "
    "I've already sent your track to the Coast Guard.":
        "Victor 叔叔，你现在回头还来得及。我已经把你的航迹发给海岸警卫队了。",
    "Let them come. We'll talk then.": "让他们来。到时候再说。",
    "Narrowest part ahead. Barely eleven yards.":
        "前面是最窄的地方，勉强十一码宽。",
    "I'll take the helm. You call distances.": "我来掌舵。你报距离。",
    "Don't lure them onto the reef on purpose.": "别故意把他们往礁石上引。",
    "I only run the safe line. We can make it. "
    "Whether they follow is their call.":
        "我只走安全航线。我们能过去。他们跟不跟，是他们自己的事。",
    "Here. Right side's closing in.": "这边。右侧在收窄。",
    "Starboard three. Hold it.": "右舷三。稳住。",
    "We're through!": "我们过来了！",
    "Look behind us.": "看我们后面。",
    "They're still coming in.": "他们还在往里跟。",
    "Mr. Harlow, we can't keep chasing! It's too narrow!":
        "Harlow 先生，不能再追了！太窄了！",
    "Get us through.": "带我们过去。",
    "Our hull's wider than theirs!": "我们的船体比他们的宽！",
    "They hit the reef!": "他们触礁了！",
    "The hull's taking water!": "船体进水了！",
    "The hull's leaking! What do we do?": "船在漏水！怎么办？",
    "Kill the engine first. Life jackets on.": "先熄火。穿上救生衣。",
    "Come back and pull us out!": "回来把我们拖出去！",
    "Can't turn around in here. Wait for rescue.": "在这里掉不了头。等救援。",
    "Coast Guard's fifteen minutes out.": "海岸警卫队十五分钟到。",
    "That's enough. Don't move your boat.": "够了。别动你的船。",
    "I'll make you pay for this.": "我会让你付出代价的。",
    "The video and the track are saved. I'll be waiting.":
        "视频和航迹都存下来了。我等着。",
    "What now?": "现在怎么办？",
    "There's something on the seabed ahead.": "前面的海底有东西。",
    "Another wreck?": "又一艘沉船？",
    "No. It looks like a building. Underwater.": "不。看起来像一座建筑。在水下。",
    "You're not diving today.": "你今天不能下潜。",
    "I know. Log the coordinates first.": "我知道。先记下坐标。",
    "Finally, something sensible.": "总算说了句靠谱的。",
    "Wait. That light's moving.": "等等。那道光在移动。",
    "We head back today.": "我们今天返航。",
    "Fine. We come back tomorrow.": "好吧。明天再来。",
}

# hand-fixed verdicts: (tag, note) -- * = PASS with a named caveat
VERDICTS = {
    "EP24-U01": ("PASS*",
                 "疑第二句句首先复读了一个 “family” 词（转写里有孤立的 family "
                 "段），建议听核第一句结尾处；台词齐、序对。"),
    "EP24-U02": ("PASS", ""),
    "EP24-U03": ("PASS", ""),
    "EP24-U04": ("PASS*",
                 "台词之后有一小段 “Show me may not” 含混声，疑非语音误听；"
                 "建议听核结尾 2 秒。台词齐、序对。"),
    "EP24-U05": ("PASS", ""),
    "EP24-U06": ("PASS",
                 "无对白条，全程静默正确；无字幕轨属正常，未生成 .srt。"),
    "EP62-U01": ("PASS", "四句连读成两段，词齐、序对。"),
    "EP62-U02": ("待听核",
                 "8.9s 处多一段含混声 “Orl'in' reaches.”，位于 “Coast Guard.” 与 "
                 "“Let them come.” 之间；期望台词齐、序对。听核 8.5–10s "
                 "是人声残片还是环境声。"),
    "EP62-U03": ("待听核",
                 "第一句后多一段无意义含混音 “Beacon brick shotch.”，疑引擎/"
                 "电流声被误听；期望台词齐、序对。听核第一句后 1 秒。"),
    "EP62-U04": ("PASS", ""),
    "EP62-U05": ("PASS",
                 "机器段级判定曾报缺 “We're through!”——逐词轨证明 2.2–3.8s "
                 "确实说了（带一声 “Ha,” 的欢呼），系段级漏转，此处纠正为 PASS。"),
    "EP62-U06": ("★重复说",
                 "第一句 “Mr. Harlow, we can't keep chasing!” 在 0.9–2.1s 与 "
                 "2.9–4.0s 连说两遍，其余台词齐、序对。放宽标准下可发："
                 "剪掉第一遍（约 0.9–2.8s），精确切点见逐词轨。"),
    "EP62-U07": ("PASS*",
                 "“They hit the reef!” 之后有一段 “She already got some pride "
                 "gap.” 含混声，疑误听；建议听核结尾。"),
    "EP63-U01": ("★疑重复说",
                 "第一句 “The hull's taking water!” 疑说两遍：约 1–3s 先有一遍"
                 "含混的（被误听成 “Donal's taking water!”），随后一遍清楚的。"
                 "需听核/看口型定切点，保留清楚的一遍。"),
    "EP63-U02": ("待听核",
                 "开头 0.0–0.6s 与结尾 8.4s 后各多一段含混声（“Come and spot "
                 "your clay.” / “Give your two.” 状）；三句正词齐、序对。"
                 "听核头尾两处。"),
    "EP63-U03": ("PASS", ""),
    "EP63-U04": ("PASS", ""),
    "EP63-U05": ("PASS", ""),
    "EP63-U06": ("PASS", ""),
}


def ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def words_srt(words: list[dict]) -> str:
    out = []
    for i, w in enumerate(words):
        start = float(w["start"])
        end = float(w["end"])
        if end <= start:
            end = start + 0.25
        out.append(f"{i + 1}\n{ts(start)} --> {ts(end)}\n{w['word']}\n")
    return "\n".join(out)


def main() -> int:
    rows = {r.get("unit") or Path(r.get("video", "")).stem: r
            for r in json.loads(REPORT.read_text(encoding="utf-8"))}
    for unit in UNITS:
        d = VERIFY / unit / "wenxi"
        mp4 = sorted(d.glob("*.mp4"))[-1]
        stem = mp4.stem
        seg_src = TMP_VIDEOS / f"{unit}.srt"
        if seg_src.exists():
            shutil.copyfile(seg_src, d / f"{stem}.srt")
        words = json.loads(
            (d / "candidate_audit.json").read_text(encoding="utf-8"))["words"]
        (d / f"{stem}_words.srt").write_text(words_srt(words), encoding="utf-8")

        r = rows.get(unit) or {}
        expected = r.get("expected_lines") or []
        heard = [s.get("text", "") for s in (r.get("segments") or [])]
        tag, note = VERDICTS[unit]
        lines = [f"# {unit} 对白审核", "", f"判定：**{tag}**", ""]
        lines.append("## 期望台词")
        if expected:
            for e in expected:
                lines.append(f"- EN: {e}")
                if ZH.get(e):
                    lines.append(f"  中：{ZH[e]}")
        else:
            lines.append("- （无对白）")
        lines += ["", "## 实际听到（ASR 段级）"]
        if heard:
            lines += [f"- {h}" for h in heard]
        else:
            lines.append("- （无语音）")
        if note:
            lines += ["", "## 备注", note]
        lines += ["",
                  "词轨：同目录 `<mp4名>.srt`（段级）与 `<mp4名>_words.srt`"
                  "（逐词，剪辑切点用逐词轨）。"]
        (d / "dialogue_check.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        print(f"{unit}: {tag} srt={'Y' if seg_src.exists() else 'N'} "
              f"words={len(words)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
