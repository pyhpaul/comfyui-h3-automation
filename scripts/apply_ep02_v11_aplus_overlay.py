#!/usr/bin/env python3
"""Apply A+ overlay to EP02 v11 manual-call TXT units (fork only)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("/mnt/c/Users/lxy/Downloads/H3-EP01-EP03-调用包-v11-ep02-aplus/EP02")
ASSET_LINE = re.compile(r"^(\d+)\.\s+(.+)\（([A-Za-z0-9\-]+)\）\s*(.*)$")
PIC_SENT = re.compile(r"@图片(\d+)[^@]*?(?=@(?:图片\d+)|$)", re.S)

# Drop matrix: unit -> asset_id to remove
DROP = {
    "ep02-s03-c1": "char-008",
    "ep02-s03-c2": "char-008",
    "ep02-s03-c3": "char-003-v1",  # Vance least critical for seal beat; keep 链/牌/大印/场景
}

# Unit-specific shot detail patches (exact old -> new), applied after globals.
SHOT_PATCHES: dict[str, list[tuple[str, str]]] = {
    "ep02-s01-c1": [
        (
            "【镜头2｜2.4–5.2秒】插入Liam左手仍撑湿石，右拇指只捏破一次粉袋，暗红粉末落到前方两步裂石，紫尘贴地卷过边缘，袋口随即瘪下去。缓推锁住手、袋口和粉末落点。",
            "【镜头2｜2.4–5.2秒】插入Liam左手仍撑湿石，右手拇指与食指只捏破一次诱兽粉袋袋口，暗红粉末落到前方两步裂石表面；紫尘贴地卷过裂石边缘后停住，袋口随即瘪下、粉末不再新落。缓推锁住手、瘪袋口和粉末落点，粉袋外形与参考图一致。",
        ),
        (
            "【镜头3｜5.2–8.0秒】匹配切回Vance，Vance不前移，后脚先踩实断石，双手把巨剑柄端压向腹前，目光从粉末扫到断墙开口。双人中景保留Liam左前、Vance右后和粉末的纵深。",
            "【镜头3｜5.2–8.0秒】匹配切回Vance，Vance不前移，后脚先踩实断石，双手把巨剑柄端压向腹前使剑尖斜垂可控；目光先落到前方贴地粉末，再扫到正前断墙开口。双人中景保留Liam左前裂石、Vance右后断石和粉末落点的同一纵深，巨剑外形不变。",
        ),
    ],
    "ep02-s01-c2": [
        (
            "【镜头1｜0.0–3.0秒】硬切到低机位，腐化腐化潜伏兽已低伏在扑击中段，前爪越过粉末砸进裂石，碎石斜打向Liam右脸侧；腐化潜伏兽的肩背仍压向前方。镜头平稳后拉给爪击留出落点。",
            "【镜头1｜0.0–3.0秒】承接切：前约一秒仍锁Liam左前裂石旁、Vance右后断石与贴地粉末；随即低机位跟入腐化潜伏兽扑击中段，前爪越过粉末砸进裂石，碎石斜打向Liam右脸侧，兽肩背继续压向前方。镜头平稳后拉给爪击留出落点，粉末落点不重置。",
        ),
        (
            "【镜头2｜3.0–6.0秒】动作匹配切，Liam左膝贴湿泥，右脚向后蹬开，腰背沿兽腹下沿压低成贴地弧线；背刺只拖开竖领外缘，后颈仍被衣领遮住，巨爪抓空石壁带出火星。侧向中景随Liam横移至右后断石左侧。",
            "【镜头2｜3.0–6.0秒】动作匹配切，Liam左膝贴湿泥，右脚向后蹬开，腰背沿兽腹下沿压低成贴地弧线；贴身内袋侧的瘪粉袋跟着腰线甩动但不掉落，背刺只拖开竖领外缘，后颈仍被衣领遮住；巨爪抓空石壁带出火星。侧向中景随Liam横移至右后断石左侧。",
        ),
        (
            "【镜头3｜6.0–8.0秒】承接火星落泥，腐化腐化潜伏兽前爪抓空却未减速，肩背继续冲向右后断石；Vance的剑柄顶在腹前，右脚碾住断石边缘等待。广角锁住Liam躲出的空位、腐化腐化潜伏兽方向和剑路。",
            "【镜头3｜6.0–8.0秒】承接火星落泥，腐化潜伏兽前爪抓空却未减速，肩背继续冲向右后断石；Vance双手把剑柄顶在腹前，右脚碾住断石边缘等待斩击窗口。广角锁住Liam躲出的空位、兽冲势与巨剑剑路，断石与粉末位置不漂。",
        ),
    ],
    "ep02-s01-c3": [
        (
            "【镜头2｜1.8–5.5秒】承接转髋，Vance双手巨剑从右肩斜切进腐化腐化潜伏兽颈部外层骨甲，剑锋卡住，双臂被反震压低，腐化腐化潜伏兽颈侧向左折而未断。镜头随剑势斜移，Liam留在左侧低位盯接触点。",
            "【镜头2｜1.8–5.5秒】承接转髋，Vance双手巨剑从右肩斜切进腐化潜伏兽颈部外层骨甲，刃口陷入骨甲缝后卡住；双臂被反震压低，兽颈侧向左折而未断。镜头随剑势斜移，Liam留在左侧低位盯剑脊与骨甲接触点。",
        ),
        (
            "【镜头3｜5.5–7.0秒】插入卡刃处，Vance双腕向下沉后把肩线沉回，腐化腐化潜伏兽前爪在泥里拖出沟，余重仍压在剑上。短长焦锁住剑脊、骨甲裂口和前爪泥沟。",
            "【镜头3｜5.5–7.0秒】插入卡刃处，Vance双腕向下沉后把肩线沉回，腐化潜伏兽前爪在泥里拖出沟，余重仍压在卡住的剑脊上。短长焦锁住剑脊、骨甲裂口和前爪泥沟，刃口不脱离骨缝。",
        ),
        (
            "【镜头4｜7.0–10.0秒】动作匹配切，Vance再沉右肩把刃口推穿，黑血沿剑脊和近护手喷开，斜溅到Vance右肩甲与Liam右颊下颌；兽首砸进两人之间湿泥，后腿留一次余颤。低机位随下坠短促下压后锁住。",
            "【镜头4｜7.0–10.0秒】动作匹配切，Vance再沉右肩把刃口推穿骨甲，黑血沿剑脊和近护手喷开，斜溅到Vance右肩甲与Liam右颊下颌；兽首砸进两人之间湿泥，后腿留一次余颤，骨核仍封在尸首内未取出。低机位随下坠短促下压后锁住。",
        ),
    ],
    "ep02-s01-c4": [
        (
            "【镜头1｜0.0–2.6秒】后腿最后一次抽搐弹起泥点后停住，Liam才把右手抵进骨缝取出骨核，手背擦过右颊却只把黑血抹得更暗。尸体左侧中近景缓推，后腿、骨核和污损同层可读。",
            "【镜头1｜0.0–2.6秒】后腿最后一次抽搐弹起泥点后停住，Liam才把右手抵进兽首骨缝取出骨核，指节抠住核缘拔出；手背擦过右颊却只把黑血抹得更暗，骨核留在右掌。尸体左侧中近景缓推，后腿、掌心骨核和污损同层可读。",
        ),
    ],
    "ep02-s01-c5": [
        (
            "【镜头2｜3.8–7.8秒】Liam不后退，右手从剑尖下方收回，把骨核塞进贴身内袋并用掌根压平袋口；Liam侧身越过兽首，左靴先踏湿泥，衣摆慢半拍扫过泥面。全身中景横移，收核、剑尖、尸体与帐篷出口保持一条动线。",
            "【镜头2｜3.8–7.8秒】Liam不后退，右手从剑尖下方收回，把骨核塞进贴身内袋并用掌根压平袋口使核形不再外露；Liam侧身越过兽首，左靴先踏湿泥，衣摆慢半拍扫过泥面。全身中景横移，收核、剑尖、尸体与帐篷出口保持一条动线。",
        ),
        (
            "【镜头3｜7.8–10.0秒】硬切到尸体后方，Vance斜收巨剑，剑尖拖湿泥划出短黑线；等Liam越尸后才同向跟上，二人朝帆布帐篷出口移动。低角度广角留稳定落幅。",
            "【镜头3｜7.8–10.0秒】承接切到尸体后方，Vance斜收巨剑，剑尖拖湿泥划出短黑线；等Liam越尸后才同向跟上，二人朝帆布帐篷出口移动，骨核已在Liam内袋不外露。低角度广角留稳定落幅。",
        ),
    ],
    "ep02-s02-c1": [
        (
            "【镜头1｜0.0–2.6秒】门帘落回后建立三人隔案位置，Liam从内袋取骨核放到长案左端托盘，Recruiter不碰，Vance在右后看住Liam双手。中景锁住托盘、水晶座与调派牌位的流程纵深。",
            "【镜头1｜0.0–2.6秒】门帘落回后建立三人隔案位置，Liam右手从贴身内袋取出骨核，掌心朝上放到长案左端锈蚀金属托盘中央后收回；Recruiter不碰，Vance在右后看住Liam双手。中景锁住托盘、中央水晶座与调派牌位的流程纵深。",
        ),
        (
            "【镜头2｜2.6–5.8秒】插入Recruiter用夹钳夹起骨核，转动一次看清裂纹后放回托盘，金属碰响落稳。手部近景让骨核从Liam手中彻底转移。",
            "【镜头2｜2.6–5.8秒】插入Recruiter用夹钳夹起托盘中的骨核，转动一次看清裂纹后放回托盘原位，金属碰响落稳，骨核不再回到Liam手里。手部近景让骨核所有权转移可读。",
        ),
    ],
    "ep02-s02-c2": [
        (
            "【镜头1｜0.0–4.3秒】第一帧Liam右掌已经平贴水晶，水晶表面没有发光也没有掌心倒影；Liam的肩膀微塌，呼吸停一拍。手与水晶中近景锁定机位，让死寂停住。",
            "【镜头1｜0.0–4.3秒】承接切：首帧续上Liam立于水晶座前、骨核仍在左端托盘；右掌平贴共鸣水晶表面，水晶不发光也无掌心倒影，Liam肩线微塌、呼吸停一拍。手与水晶中近景锁定机位，托盘骨核仍在左前景外缘可读。",
        ),
        (
            "【镜头2｜4.3–7.0秒】反打Recruiter，Recruiter只看水晶一眼再看Liam，平声说：（Affinity: zero.） Liam右手离开水晶半寸，Vance在右后保持沉默。中景把三人的流程位置钉住。",
            "【镜头2｜4.3–7.0秒】反打Recruiter，Recruiter只看水晶一眼再看Liam，平声说：（Affinity: zero.） Liam右手离开水晶半寸悬停、掌心朝下，水晶仍死寂；Vance在右后保持沉默。中景把三人位置与左端托盘骨核钉住。",
        ),
    ],
    "ep02-s02-c3": [
        (
            "【镜头1｜0.0–2.6秒】Recruiter抬起红色废品印章，垂直压到长案右端同一张调派牌，闷响后红印完整留纸。俯角中近景锁住印章、牌面与Liam右颊污损。",
            "【镜头1｜0.0–2.6秒】Recruiter抬起红色废品印章，垂直压到长案右端同一张调派牌，闷响后红印完整留纸；印章抬起后牌面红印不糊。俯角中近景锁住印章、牌面与Liam右颊污损，左端托盘骨核仍在。",
        ),
        (
            "【镜头3｜5.2–10.0秒】顺着Liam看红印的视线切回，Liam停住一拍，右手从水晶上方落回身体侧面，左手沿内袋确认骨核已经不在；再抬眼时转向左侧门帘，冷光切过竖领和右颊黑血。中近景极缓后拉，红印和出口保持同一纵深。",
            "【镜头3｜5.2–10.0秒】顺着Liam看红印的视线切回，Liam停住一拍，右手从水晶上方落回身体侧面，左手沿内袋确认骨核已经不在（核仍在托盘）；再抬眼时转向左侧门帘，冷光切过竖领和右颊黑血。中近景极缓后拉，红印调派牌和出口保持同一纵深。",
        ),
    ],
    "ep02-s03-c1": [
        (
            "【镜头1｜0.0–2.2秒】建立五人纵深，Vance把囚链锁环扣上Liam左腕，锁舌咬合后链节还带轻微余响；Liam不抽手，只把视线越过点验台投向右侧九锁门。中景锁住左前、右后与门的纵深。",
            "【镜头1｜0.0–2.2秒】建立台前纵深，Vance双手把囚链锁环扣上Liam左腕，锁舌咬合咔一声后链节轻响；Liam不抽手，只把视线越过点验台投向右侧九锁门。中景锁住左前Liam、右后Vance与门的纵深，锁环贴合腕骨。",
        ),
        (
            "【镜头2｜2.2–4.4秒】插入左腕，锁环闭合，Vance拇指压过锁舌确认，Liam右手保持空。手部近景让金属受力和皮肤压痕可读。",
            "【镜头2｜2.2–4.4秒】插入左腕，锁环已闭合，Vance拇指压过锁舌确认扣死，链环贴紧皮肤压出浅痕；Liam右手保持空、不碰锁。手部近景让金属受力、锁舌与皮肤压痕可读。",
        ),
        (
            "【镜头3｜4.4–8.0秒】反打Thorne，Thorne读着红印调派牌，目光不从纸面抬起地说：（Null affinity. Sector Nine.） Liam在前景虚化中仍望向闸门，Vance站在Liam右后。短长焦压住牌、嘴和门的方向。",
            "【镜头3｜4.4–8.0秒】反打Thorne，Thorne双手持红印调派牌贴近视线，目光不从纸面抬起地说：（Null affinity. Sector Nine.） Liam在前景虚化中仍望向闸门，左腕链垂向台面；Vance站在Liam右后。短长焦压住牌面红印、嘴和门的方向。",
        ),
    ],
    "ep02-s03-c2": [
        (
            "【镜头1｜0.0–3.9秒】Liam先低头看锁环，左腕链节擦过点验台边沿；Liam抬眼越过Thorne，右手只指向一次右侧九锁门，平而准地说：（The Abyssal Menagerie.） 左腕仍被链重拉低。中近景把锁腕、右手指向与门构成清晰三角。",
            "【镜头1｜0.0–3.9秒】承接切：续上Liam左腕已锁、Thorne持红印牌；Liam先低头看锁环，左腕链节擦过点验台边沿发出轻金属声；抬眼越过Thorne，右手只指向一次右侧九锁门，平而准地说：（The Abyssal Menagerie.） 左腕仍被链重拉低。中近景把锁腕、右手指向与门构成清晰三角。",
        ),
        (
            "【镜头3｜7.8–10.0秒】匹配切到门侧，重装守卫先把铁钩收紧，重装重装守卫乙慢半拍才停住原本的换重心；Liam左腕被第一记收紧向下带一寸，肩线随后定住，视线仍留在九锁门。广角锁住两名重装守卫、锁腕与闸门。",
            "【镜头3｜7.8–10.0秒】匹配切到门侧，台边守卫先把铁钩收紧，门侧守卫慢半拍才停住换重心；Liam左腕被第一记收紧向下带一寸，肩线随后定住，视线仍留在九锁门，竖领仍遮血契。广角锁住台边与门侧守卫、锁腕与闸门。",
        ),
    ],
    "ep02-s03-c3": [
        (
            "【镜头1｜0.0–3.7秒】Liam用锁住左腕的手掀开竖领，后颈血契从衣领上方暴露；Liam抬眼向Thorne说：（Then sign me in.） 肩颈中近景缓推，锁链从左下前景拉向台面。",
            "【镜头1｜0.0–3.7秒】承接切：续上左腕锁链受力；Liam用锁住的左手掀开竖领，后颈血契从衣领上方暴露；抬眼向Thorne说：（Then sign me in.） 肩颈中近景缓推，锁链从左下前景拉向台面，红印调派牌仍在台面可读。",
        ),
        (
            "【镜头2｜3.7–5.8秒】反打Thorne，红印牌摊在点验台上，Thorne把黑铁大印举到牌上方，眼睛只停在Liam露出的血契一瞬。中近景让红印仍清楚可读。",
            "【镜头2｜3.7–5.8秒】反打Thorne，红印调派牌摊在点验台上，Thorne右手把黑铁大印举到牌正上方对准印位，眼睛只停在Liam露出的血契一瞬。中近景让红印与大印底部同框清楚可读。",
        ),
        (
            "【镜头3｜5.8–8.0秒】动作匹配切，黑铁大印垂直落在同一张红印调派牌上，闷响后批准印完成；Liam把衣领收回但左腕锁链仍在，转身与右侧九锁门同框朝门，Vance留在右后。双层中景留稳定落幅给印章和闸门。",
            "【镜头3｜5.8–8.0秒】动作匹配切，黑铁大印垂直落在同一张红印调派牌上，闷响后黑铁批准印叠在红印之上完成；Liam把衣领收回但左腕锁链仍锁死、双手空，转身与右侧九锁门同框朝门。双层中景留稳定落幅给牌面双印和闸门。",
        ),
    ],
}


def distill_access(access: str) -> str:
    """Visible opening state only; strip latent/ops jargon."""
    t = access
    # cut at latent ops clauses
    for stop in (
        "H3 父条",
        "本条 0.00",
        "0.00–1.00",
        "原始 H3 AV latent",
        "AV latent",
        "重生成",
        "不得另起开场",
    ):
        if stop in t:
            t = t.split(stop, 1)[0]
    t = t.strip(" ；;。.\n")
    # drop chain meta prefixes but keep after first colon content when present
    t = re.sub(r"^承接\s+ep\d+-s\d+-c\d+[：:]", "", t).strip()
    t = re.sub(r"^本链首条 U（[^）]+），无父片视频视觉锚定。", "", t).strip()
    t = re.sub(r"^以本条已绑定的角色、场景、道具资产和上述 0 秒状态建立开场[：:]", "", t).strip()
    t = re.sub(r"跨 EP01 独立状态重锚。?", "", t).strip()
    t = re.sub(r"跨场独立状态重锚。?", "", t).strip()
    # cleanup
    t = re.sub(r"\s+", " ", t).strip(" ；;")
    if not t:
        return ""
    if not t.endswith("。"):
        t += "。"
    return t


def drop_asset(text: str, drop_id: str) -> str:
    lines = text.splitlines()
    kept_assets: list[str] = []
    new_lines: list[str] = []
    in_upload = False
    for line in lines:
        if line.startswith("【上传资产路径与顺序】"):
            in_upload = True
            new_lines.append(line)
            continue
        if in_upload and line.startswith("【"):
            in_upload = False
        if in_upload:
            m = ASSET_LINE.match(line.strip())
            if m and m.group(3) == drop_id:
                continue
            if m:
                kept_assets.append(m.group(3))
                # renumber later
                new_lines.append(line)
                continue
        new_lines.append(line)

    # renumber upload lines
    n = 0
    renum_lines: list[str] = []
    in_upload = False
    for line in new_lines:
        if line.startswith("【上传资产路径与顺序】"):
            in_upload = True
            renum_lines.append(line)
            continue
        if in_upload and line.startswith("【"):
            in_upload = False
        if in_upload:
            m = ASSET_LINE.match(line.strip())
            if m:
                n += 1
                rest = line.strip()
                rest = ASSET_LINE.sub(
                    lambda mm: f"{n}. {mm.group(2)}（{mm.group(3)}）{mm.group(4)}",
                    rest,
                    count=1,
                )
                # preserve original indent-less format
                renum_lines.append(rest)
                continue
        renum_lines.append(line)

    text2 = "\n".join(renum_lines)
    # drop matching @图片 sentence that mentions the dropped role roughly:
    # map by finding which @图片N line referenced this asset via upload order index.
    # After drop, rebuild picture mapping from remaining upload order: Picture i = i-th asset.
    # Remove the @图片 sentence whose content is about 重装守卫 / Vance depending on drop.
    drop_hints = {
        "char-008": ["重装守卫", "重甲重装"],
        "char-003-v1": ["Vance", "右肩甲有黑血的Vance"],
    }
    hints = drop_hints.get(drop_id, [drop_id])

    def _constraint_block(s: str) -> tuple[str, str, str]:
        if "【画面总约束】" not in s:
            return s, "", ""
        pre, rest = s.split("【画面总约束】", 1)
        # first paragraph of @图片 lines usually ends at blank line
        parts = rest.split("\n\n", 1)
        head = parts[0]
        tail = parts[1] if len(parts) > 1 else ""
        return pre, head, tail

    pre, head, tail = _constraint_block(text2)
    if head:
        # split @图片 sentences
        sents = re.findall(r"@图片\d+[^@]*", head)
        suffix = head
        for s in sents:
            suffix = suffix.replace(s, "", 1)
        kept = []
        for s in sents:
            if any(h in s for h in hints):
                continue
            kept.append(s)
        # renumber pictures 1..N
        renum = []
        for i, s in enumerate(kept, start=1):
            renum.append(re.sub(r"@图片\d+", f"@图片{i}", s, count=1))
        new_head = "".join(renum) + suffix
        # clean double spaces
        new_head = re.sub(r"[ \t]{2,}", " ", new_head)
        text2 = pre + "【画面总约束】" + new_head
        if tail:
            text2 = text2 + "\n\n" + tail
    return text2


def strip_text_locked_pictures(text: str) -> tuple[str, list[str]]:
    """Drop @图片N that map to non-uploadable asset lines; renumber to uploadable order.

    Pack lines may include B-level text-locked props (不可上传). Orchestrator only
    uploads real stills as Picture 1..N, so those @图片 sentences must be removed
    and later pictures renumbered, or Picture N would bind to the wrong still.
    """
    notes: list[str] = []
    lines = text.splitlines()
    # collect upload-section asset ids in order + which are uploadable
    assets: list[tuple[str, bool]] = []
    in_upload = False
    for line in lines:
        if line.startswith("【上传资产路径与顺序】"):
            in_upload = True
            continue
        if in_upload and line.startswith("【"):
            break
        if not in_upload:
            continue
        m = ASSET_LINE.match(line.strip())
        if not m:
            continue
        aid = m.group(3)
        rest = m.group(4)
        rel_m = re.search(r"包内路径：([^\s｜|]+)", rest)
        rel = (rel_m.group(1).replace("\\", "/") if rel_m else "")
        if rel == "不适用":
            rel = ""
        uploadable = "文件存在" in rest and bool(rel)
        assets.append((aid, uploadable))

    non_up_indices = {i for i, (_aid, up) in enumerate(assets, start=1) if not up}
    if not non_up_indices:
        return text, notes

    if "【画面总约束】" not in text:
        return text, notes
    pre, rest = text.split("【画面总约束】", 1)
    parts = rest.split("\n\n", 1)
    head = parts[0]
    tail = parts[1] if len(parts) > 1 else ""
    sents = re.findall(r"@图片\d+[^@]*", head)
    if not sents:
        return text, notes
    suffix = head
    for s in sents:
        suffix = suffix.replace(s, "", 1)
    kept: list[str] = []
    for s in sents:
        m = re.match(r"@图片(\d+)", s)
        if m and int(m.group(1)) in non_up_indices:
            notes.append(f"drop_text_pic:@图片{m.group(1)}")
            continue
        kept.append(s)
    renum = [re.sub(r"@图片\d+", f"@图片{i}", s, count=1) for i, s in enumerate(kept, start=1)]
    new_head = "".join(renum) + suffix
    new_head = re.sub(r"[ \t]{2,}", " ", new_head)
    out = pre + "【画面总约束】" + new_head
    if tail:
        out = out + "\n\n" + tail
    return out, notes


def inject_continuity(text: str, access: str, is_head: bool) -> str:
    if is_head:
        return text
    distilled = distill_access(access)
    if not distilled:
        return text
    block = (
        "【开场续态｜承接】"
        + distilled
        + "开场约一秒内保持上述人物站位、朝向、道具落点与环境光声连续，再进入下列逐镜；不得另起无关开场或重置已交出的物态。"
    )
    if "【开场续态｜承接】" in text:
        return text
    if "【逐镜执行】" not in text:
        return text
    return text.replace("【逐镜执行】", block + "\n\n【逐镜执行】", 1)


def soft_hard_cuts(text: str, is_head: bool) -> str:
    if is_head:
        # still soft intra-unit hard cuts that fight continuity inside a unit? keep for heads
        return text.replace("硬切到", "镜头切到").replace("硬切", "镜头切")
    return (
        text.replace("硬切到", "承接切到")
        .replace("硬切", "承接切")
    )


def process_unit(path: Path) -> dict:
    uid = path.stem
    raw = path.read_text(encoding="utf-8")
    text = raw
    notes: list[str] = []

    # global typo
    if "腐化腐化" in text:
        c = text.count("腐化腐化")
        text = text.replace("腐化腐化", "腐化")
        notes.append(f"fix_dup_fuhua×{c}")
    if "重装重装" in text:
        text = text.replace("重装重装", "重装")
        notes.append("fix_dup_guard")

    access = ""
    if "【H3 latent 接入文字】" in text:
        access = text.split("【H3 latent 接入文字】", 1)[1].split("【", 1)[0].strip()
    is_head = ("本链首条" in access) or ("无父片" in access)

    if uid in DROP:
        text = drop_asset(text, DROP[uid])
        notes.append(f"drop:{DROP[uid]}")

    text, locked_notes = strip_text_locked_pictures(text)
    notes.extend(locked_notes)

    text = soft_hard_cuts(text, is_head=is_head)
    if not is_head:
        notes.append("soft_hard_cut")

    text = inject_continuity(text, access, is_head=is_head)
    if not is_head:
        notes.append("inject_continuity")

    def _patch_variants(old: str) -> list[str]:
        variants = [old]
        a = old.replace("腐化腐化", "腐化").replace("重装重装", "重装")
        if a not in variants:
            variants.append(a)
        for base in list(variants):
            soft = (
                base.replace("硬切到", "承接切到")
                .replace("硬切", "承接切")
            )
            if soft not in variants:
                variants.append(soft)
            soft_head = base.replace("硬切到", "镜头切到").replace("硬切", "镜头切")
            if soft_head not in variants:
                variants.append(soft_head)
        return variants

    for old, new in SHOT_PATCHES.get(uid, []):
        applied = False
        for cand in _patch_variants(old):
            if cand in text:
                text = text.replace(cand, new, 1)
                notes.append("shot_patch")
                applied = True
                break
        if not applied:
            notes.append(f"MISS_PATCH:{old[:24]}")

    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return {"unit": uid, "head": is_head, "notes": notes, "changed": text != raw}


def main() -> None:
    report = []
    for p in sorted(ROOT.glob("ep02-*.txt")):
        report.append(process_unit(p))
    out = Path("/home/linux_dev/projects/comfyui-h3-automation/runs/ep02_v11_aplus_overlay_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
