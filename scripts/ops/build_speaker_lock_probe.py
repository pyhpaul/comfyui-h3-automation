#!/usr/bin/env python3
"""Build speaker-lock probe workflows (see docs/ops/2026-10-22-speaker-lock-probe-plan.md).

Each probe is a single-speaker sub-unit: the non-speaker's reference image
is removed from the workflow entirely (not merely described as off-frame),
the prompt is rewritten for one shot / one line, and length is set from
the line. P-A is disconnected; P-B1 chains from the production U05 latent;
P-B2 chains from P-B1's server-side saved latent.

Outputs: .cache/chaofu_probe/input/<tag>.json + <tag>.txt + manifest.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".cache/chaofu_fx21_colab/input"
DST = ROOT / ".cache/chaofu_probe/input"

COLE = ("Cole Mercer［潜水时期］ <Picture {n}>［char-001-W01］：29岁，男性，深棕色短发，"
        "发梢微湿贴着额头。蓝灰色眼睛，皮肤晒成浅古铜色，身形精瘦结实。穿着黑色"
        "长袖潜水服，胸口和肩部有深灰色拼接，黑色潜水长裤，黑色潜水靴。"
        "声线基准：29岁男性，中音区，干净偏冷，语速慢，咬字一字一顿。")
COLE_MASK = ("Cole Mercer［潜水时期·戴全面罩］ <Picture {n}>［char-001-W05］：29岁，男性，"
             "深棕色短发，蓝灰色眼睛，皮肤晒成浅古铜色，身形精瘦结实。脸上扣着黑色"
             "边框的全面罩，透明的大面窗把整张脸罩在里面，隔着面窗看得清五官，面罩"
             "下方有排气阀，左侧耳边连着一个黑色通讯模块，脑后用黑色五爪绑带固定。"
             "穿着黑色长袖潜水服，胸口和肩部有深灰色拼接，胸前没有口袋，黑色潜水"
             "长裤，黑色潜水靴。")
WADE = ("Wade Mercer <Picture {n}>［char-002-W01］：33岁，男性，金棕色短发向后梳，"
        "下颌留着修剪整齐的短胡茬。棕色眼睛，皮肤偏红润，身形壮实。穿着深酒红色"
        "长袖翻领Polo衫，深灰色休闲长裤，深棕色皮质船鞋。"
        "声线基准：33岁男性，中低音区，略带沙哑，咬字干脆。")
SCENE = ("渔船甲板 <Picture {n}>［scene-001-S01］：船头朝北，船尾朝南；入口：船尾栏杆门［南］、"
         "驾驶舱门［北］；白天阴天。参考图是东侧朝西的单幅：北侧驾驶舱和声呐在画面右，"
         "西侧海面在前方。")
MASK = ("全面罩 <Picture {n}>［prop-011］：一只潜水用的带通讯全面罩，黑色硬质边框，一整块"
        "透明的大面窗，面窗内侧下方是透明的口鼻罩；面罩正下方是带横向格栅的黑色圆形"
        "排气阀，左侧连着一个黑色方形通讯模块，模块后面接出一小段黑色线缆，两侧有几个"
        "黑色按钮和调节阀；脑后是黑色橡胶五爪绑带，绑带末端有黑色快拉扣。面罩和绑带上"
        "没有任何文字、字母、数字和标志。")
TANK = ("气瓶 <Picture {n}>［prop-004］：一只成人用的铝合金潜水气瓶，圆柱形瓶身是哑光银灰色，"
        "顶部是镀铬瓶阀，瓶阀上接着一根黑色软管和一块圆形压力表，表盘上只有简单的刻度线；"
        "瓶身背面固定着一块黑色硬质背板，连着两条黑色尼龙肩带和一条腰带，带黑色塑料卡扣。"
        "瓶身没有任何文字、数字、标签和标志。")
GOLD = ("金条 <Picture {n}>［prop-002］：一根铸造金条，长方体，顶面略小于底面，边角圆润，"
        "通体是沉甸甸的暗金色金属光泽，表面光洁，没有任何压印、文字、数字、编号和标志。")
ROPE = ("安全绳 <Picture {n}>［prop-006］：一根潜水用的安全绳，直径约一厘米的黄色编织尼龙绳，"
        "整齐地盘成一卷，绳头连着一只不锈钢扣环。")

RULES = ("人物对白只能读（）内的英文，禁止读旁白。\n"
         "（）里的每一句台词都要由点名的说话人完整说出，不省略、不改词。\n"
         "有台词的镜头里，只有点名的说话人开口，其他人嘴唇闭合。\n"
         "没有（）台词的镜头里，画面里所有人嘴唇闭合，不开口，只做表情和动作。")
MOOD = ("【氛围与画质】电影级写实真人，美国东北海岸渔船后甲板，白天阴天。漫射天光，"
        "无直射阳光，海面铁灰色，低云，色温偏冷灰。声音只用现场声：海风声、浪拍船身声、"
        "动作声和人物原声，不加配乐和字幕。")

PROMPT_A = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{SCENE.format(n=2)}
{GOLD.format(n=3)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：Wade Mercer 站在驾驶舱门口，身体面南，右手按在西侧门框上，下巴绷紧，胸口起伏。画面里只有 Wade Mercer 一个人；他的同伴在船尾方向的画外，全程不入画、不在画框边缘露脸。机位在 Wade Mercer 正南约两米，朝北拍他正面近景，机位不移动到能看见同伴的位置。

【画面内容】
场景：渔船甲板
人物：Wade Mercer
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲手持镜头，近景［Wade Mercer正面］。开头 Wade Mercer 喉头滚了一下，嘴唇闭合，看着画外的同伴，嘴角扯出一点硬邦邦的弧度；随后口型同步开口，音量适中、语速平稳、语气带着自以为占理的轻慢地说：（ You're alive, aren't you? ） Wade Mercer说完，嘴唇合上，那点弧度还挂在嘴角，目光仍落在画外同伴脸上。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Wade Mercer轻慢的反问］

【交出状态】Wade Mercer 站在驾驶舱门口面南，右手按在西侧门框上，嘴唇闭合，嘴角带一点硬邦邦的弧度，视线落在画外南侧同伴脸上；海风大，浪拍船身，发动机低速运转。
"""

PROMPT_B1 = f"""【H3 提示词】

【参考设定】
{COLE.format(n=1)}
{COLE_MASK.format(n=2)}
{SCENE.format(n=3)}
{MASK.format(n=4)}
{TANK.format(n=5)}
{ROPE.format(n=6)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：承接上一条尾态。Cole Mercer 站在船尾栏杆门东侧门柱正北、横栏内侧，身体面北，右手攥着安全绳的扣环绳头举在胸前，绳垂到他左脚边甲板上的绳盘里；气瓶背在背上，全面罩挂在胸前。机位在 Cole Mercer 北偏东约两米，朝南偏西拍他近景；另一名同伴在机位后方，全程不入画、不在画框边缘露脸。

【画面内容】
场景：渔船甲板
人物：Cole Mercer［潜水时期］
环境描述：白天，阴天，低云压着铁灰色的海面，海风渐起，浪涌更急，天色渐暗

▲缓慢推镜头，近景［Cole Mercer正面，船尾栏杆门旁］。开头约一秒 Cole Mercer 嘴唇闭合，盯着机位后方同伴的方向，一只手攥紧安全绳，指节发白；随后口型同步开口，音量压低、语速放慢、语气一字一顿地说：（ Wade. I mean it. ） Cole Mercer说完，嘴唇合上，眼睛不眨，攥绳的手没有松开，保持站立望着画外。

音频：环境音［低沉的海风声、浪拍船身的闷响］+ 动作音［安全绳被攥紧的摩擦声］+ 人物音［Cole Mercer一字一顿的叮嘱］

【H3 latent 接入文字】承接 U05：Cole 站在栏杆门东侧门柱正北、横栏内侧，面北，右手举着安全绳的扣环绳头，绳垂到他左脚边、栏杆门前甲板上的绳盘里；气瓶背在背上，全面罩挂在胸前，目光沉沉地对着舱门口方向。0.00–1.00 秒从 U05 尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。机位在 Cole 北偏东朝南，同伴在机位后方不入画。之后进入本段第一镜。

【交出状态】Cole Mercer 站在栏杆门东侧门柱正北、横栏内侧，面北，右手攥着安全绳扣环绳头举在胸前，绳垂到左脚边的绳盘里；气瓶在背上，全面罩挂在胸前，嘴唇闭合，目光沉沉望向北侧画外；天色渐暗，浪涌更急。
"""

PROMPT_B2 = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{SCENE.format(n=2)}
{ROPE.format(n=3)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：Wade Mercer 站在驾驶舱门口，身体面南，左手搭在东侧门框上，嘴角微扬，视线望向船尾。Cole Mercer 在船尾栏杆门旁，本段全程留在画外：跟拍机位在甲板东半边，朝西偏南跟拍 Wade Mercer，Cole Mercer 始终在画框右缘之外，不入画、不露脸。

【画面内容】
场景：渔船甲板
人物：Wade Mercer
环境描述：白天，阴天，低云压着铁灰色的海面，海风渐起，浪涌更急，天色渐暗

▲跟镜头，中景［Wade Mercer从驾驶舱门口走到船尾］。Wade Mercer 离开门框沿甲板中线向南走到船尾，停在栏杆门正北、绳盘旁，弯腰用右手从绳盘里拎起安全绳的另一端，在右手掌心绕一圈，直起身面朝东、看着画外的 Cole Mercer，肩膀一耸，扬起眉毛，口型同步开口，音量适中、语速不紧不慢、语气带着轻慢的笑地说：（ When have I ever really left you down there? ） Wade Mercer说完，嘴唇合上，嘴角的笑还挂着，视线仍落在画外 Cole Mercer 脸上。

音频：环境音［低沉的海风声、浪拍船身的闷响］+ 动作音［脚步声、安全绳被拎起的摩擦声］+ 人物音［Wade Mercer轻慢的反问］

【H3 latent 接入文字】承接上一段：Cole Mercer 在船尾栏杆门东侧门柱正北面北持绳（本段画外），Wade Mercer 在驾驶舱门口面南。0.00–1.00 秒从上一段尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。机位在甲板东半边，Cole Mercer 留在画框外。之后进入本段第一镜。

【交出状态】Wade Mercer 站在栏杆门正北、绳盘旁，面朝东，右手掌心绕着安全绳的另一端，嘴唇闭合，嘴角带着笑，视线落在画外东侧的 Cole Mercer 脸上；Cole Mercer 在画外持着绳的另一头；天色渐暗，浪涌更急。
"""

PROMPT_C = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{COLE.format(n=2)}
{SCENE.format(n=3)}
{GOLD.format(n=4)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：Wade Mercer 站在驾驶舱门口，身体面南，右手按在西侧门框上，下巴绷紧，胸口起伏。Cole Mercer 站在 Wade Mercer 正南约两米、面北正对 Wade Mercer；机位在 Cole Mercer 右肩正后方，画面右下前景只有 Cole Mercer 的后脑右侧、右肩和上背，深棕色短发与黑色潜水服肩部强烈失焦虚化，占画面不超过四分之一；Cole Mercer 的脸完全不在画框内，全程不转头、不回头、不侧脸，嘴不可见。Wade Mercer 在画面中央中近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Wade Mercer、Cole Mercer［潜水时期］（仅肩背前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲过肩镜头，中近景［越过 Cole Mercer 右肩拍 Wade Mercer 正面］。前景 Cole Mercer 只有后脑、右肩和上背失焦入画，全程背对机位、不转头，只有肩背随呼吸轻微起伏，不开口；Wade Mercer 开头喉头滚了一下，嘴唇闭合，看着前景的 Cole Mercer，嘴角扯出一点硬邦邦的弧度；随后口型同步开口，音量适中、语速平稳、语气带着自以为占理的轻慢地说：（ You're alive, aren't you? ） Wade Mercer说完，嘴唇合上，那点弧度还挂在嘴角，目光仍落在 Cole Mercer 脸的方向。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Wade Mercer轻慢的反问］

【交出状态】Wade Mercer 站在驾驶舱门口面南，右手按在西侧门框上，嘴唇闭合，嘴角带一点硬邦邦的弧度，视线落在 Cole Mercer 脸上；Cole Mercer 在其正南面北，前景只露后脑、右肩和上背，背对机位；海风大，浪拍船身，发动机低速运转。
"""

PROMPT_B1R = f"""【H3 提示词】

【参考设定】
{COLE.format(n=1)}
{SCENE.format(n=2)}
{MASK.format(n=3)}
{TANK.format(n=4)}
{ROPE.format(n=5)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：承接上一条尾态。Cole Mercer 站在船尾栏杆门东侧门柱正北、横栏内侧，身体面北，右手攥着安全绳的扣环绳头举在胸前，绳垂到他左脚边甲板上的绳盘里，左手扶着栏杆横栏；气瓶背在背上，全面罩挂在胸前带子上。Cole Mercer 双手全程各有占用：右手不松安全绳、左手不离横栏，全程不碰全面罩、不抬起全面罩、不把全面罩戴到脸上。机位在 Cole Mercer 北偏东约两米，朝南偏西拍他近景；另一名同伴在机位后方，全程不入画、不在画框边缘露脸。

【画面内容】
场景：渔船甲板
人物：Cole Mercer［潜水时期］
环境描述：白天，阴天，低云压着铁灰色的海面，海风渐起，浪涌更急，天色渐暗

▲缓慢推镜头，近景［Cole Mercer正面，船尾栏杆门旁］。开头约一秒 Cole Mercer 嘴唇闭合，盯着机位后方同伴的方向，右手攥紧安全绳，指节发白，左手扶着横栏，全面罩始终挂在胸前不动；随后口型同步开口，音量压低、语速放慢、语气一字一顿地说：（ Wade. I mean it. ） Cole Mercer说完，嘴唇合上，眼睛不眨，攥绳的手没有松开，保持站立望着画外。

音频：环境音［低沉的海风声、浪拍船身的闷响］+ 动作音［安全绳被攥紧的摩擦声］+ 人物音［Cole Mercer一字一顿的叮嘱］

【H3 latent 接入文字】承接 U05：Cole 站在栏杆门东侧门柱正北、横栏内侧，面北，右手举着安全绳的扣环绳头，绳垂到他左脚边、栏杆门前甲板上的绳盘里；气瓶背在背上，全面罩挂在胸前，目光沉沉地对着舱门口方向。0.00–1.00 秒从 U05 尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。机位在 Cole 北偏东朝南，同伴在机位后方不入画。之后进入本段第一镜。

【交出状态】Cole Mercer 站在栏杆门东侧门柱正北、横栏内侧，面北，右手攥着安全绳扣环绳头举在胸前，绳垂到左脚边的绳盘里，左手扶着横栏；气瓶在背上，全面罩挂在胸前不动，嘴唇闭合，目光沉沉望向北侧画外；天色渐暗，浪涌更急。
"""

PROMPT_E = f"""【H3 提示词】

【参考设定】
{COLE.format(n=1)}
{WADE.format(n=2)}
{SCENE.format(n=3)}
{MASK.format(n=4)}
{TANK.format(n=5)}
{ROPE.format(n=6)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：承接上一条尾态。Cole Mercer 站在船尾栏杆门东侧门柱正北、横栏内侧，身体面北，右手攥着安全绳的扣环绳头举在胸前，绳垂到他左脚边甲板上的绳盘里，左手扶着栏杆横栏；气瓶背在背上，全面罩挂在胸前带子上，双手全程各有占用，不碰、不抬全面罩。Wade Mercer 站在 Cole Mercer 正北约两米、面南正对 Cole Mercer；机位在 Wade Mercer 左肩正后方，画面左下前景只有 Wade Mercer 的后脑左侧、左肩和上背，金棕色短发与深酒红色 Polo 衫肩部强烈失焦虚化，占画面不超过四分之一；Wade Mercer 的脸完全不在画框内，全程不转头、不回头、不侧脸，嘴不可见。Cole Mercer 在画面中央近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Cole Mercer［潜水时期］、Wade Mercer（仅肩背前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风渐起，浪涌更急，天色渐暗

▲过肩镜头，近景［越过 Wade Mercer 左肩拍 Cole Mercer 正面，船尾栏杆门旁］。前景 Wade Mercer 只有后脑、左肩和上背失焦入画，全程背对机位、不转头，只有肩背随呼吸轻微起伏，不开口；Cole Mercer 开头约一秒嘴唇闭合，盯着前景的 Wade Mercer，右手攥紧安全绳，指节发白，左手扶着横栏，全面罩始终挂在胸前不动；随后口型同步开口，音量压低、语速放慢、语气一字一顿地说：（ Wade. I mean it. ） Cole Mercer说完，嘴唇合上，眼睛不眨，攥绳的手没有松开，保持站立望着 Wade Mercer。

音频：环境音［低沉的海风声、浪拍船身的闷响］+ 动作音［安全绳被攥紧的摩擦声］+ 人物音［Cole Mercer一字一顿的叮嘱］

【H3 latent 接入文字】承接 U05：Cole 站在栏杆门东侧门柱正北、横栏内侧，面北，右手举着安全绳的扣环绳头，绳垂到他左脚边、栏杆门前甲板上的绳盘里；气瓶背在背上，全面罩挂在胸前，目光沉沉地对着舱门口方向；Wade 在 Cole 正北面南。0.00–1.00 秒从 U05 尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。机位在 Wade 左肩后方朝南，Wade 只以肩背前景入画。之后进入本段第一镜。

【交出状态】Cole Mercer 站在栏杆门东侧门柱正北、横栏内侧，面北，右手攥着安全绳扣环绳头举在胸前，绳垂到左脚边的绳盘里，左手扶着横栏；气瓶在背上，全面罩挂在胸前不动，嘴唇闭合，目光沉沉望向 Wade Mercer；Wade Mercer 在其正北面南，前景只露后脑、左肩和上背，背对机位；天色渐暗，浪涌更急。
"""

PROMPT_D = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{COLE.format(n=2)}
{SCENE.format(n=3)}
{ROPE.format(n=4)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：Wade Mercer 站在驾驶舱门口，身体面南，左手搭在东侧门框上，嘴角微扬，视线望向船尾。Cole Mercer 站在船尾栏杆门东侧门柱正北、横栏内侧，身体面北，手里攥着安全绳一端。跟拍机位在甲板东半边；Wade Mercer 说台词时，机位停在 Cole Mercer 右肩正后方，画面右下前景只有 Cole Mercer 的后脑右侧、右肩和上背，强烈失焦虚化，占画面不超过四分之一；Cole Mercer 的脸完全不在画框内，不转头、不回头、不侧脸，嘴不可见。Wade Mercer 在画面中央中近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Wade Mercer、Cole Mercer［潜水时期］（仅肩背前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风渐起，浪涌更急，天色渐暗

▲跟镜头转过肩，中景转中近景［Wade Mercer从驾驶舱门口走到船尾，停在 Cole Mercer 对面］。Wade Mercer 离开门框沿甲板中线向南走到船尾，停在栏杆门正北、绳盘旁，正面朝南对着 Cole Mercer，弯腰用右手从绳盘里拎起安全绳的另一端，在右手掌心绕一圈，直起身看着 Cole Mercer，肩膀一耸，扬起眉毛；此时前景是 Cole Mercer 失焦的后脑、右肩和上背，Cole Mercer 背对机位、不转头、不开口；Wade Mercer 口型同步开口，音量适中、语速不紧不慢、语气带着轻慢的笑地说：（ When have I ever really left you down there? ） Wade Mercer说完，嘴唇合上，嘴角的笑还挂着，视线仍落在 Cole Mercer 脸上。

音频：环境音［低沉的海风声、浪拍船身的闷响］+ 动作音［脚步声、安全绳被拎起的摩擦声］+ 人物音［Wade Mercer轻慢的反问］

【H3 latent 接入文字】承接上一段：Cole Mercer 在船尾栏杆门东侧门柱正北面北持绳，Wade Mercer 在驾驶舱门口面南。0.00–1.00 秒从上一段尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。之后跟拍 Wade Mercer 向南走位，台词机位停在 Cole Mercer 右肩后方，Cole Mercer 只以肩背前景入画。

【交出状态】Wade Mercer 站在栏杆门正北、绳盘旁，面南正对 Cole Mercer，右手掌心绕着安全绳的另一端，嘴唇闭合，嘴角带着笑，视线落在 Cole Mercer 脸上；Cole Mercer 在其正南面北持着绳的另一头，前景只露后脑、右肩和上背，背对机位；天色渐暗，浪涌更急。
"""

PROMPT_F = f"""【H3 提示词】

【参考设定】
{COLE.format(n=1)}
{WADE.format(n=2)}
{SCENE.format(n=3)}
{MASK.format(n=4)}
{GOLD.format(n=5)}
{TANK.format(n=6)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：承接上一段尾态。Wade Mercer 站在驾驶舱门口，身体面南，右手按在西侧门框上；Cole Mercer 站在 Wade Mercer 正南约一臂远，身体面北正对 Wade Mercer，右臂箍着六根金条贴在胸前，左手垂着，全面罩挂在胸前，气瓶背在背上。反打机位在 Wade Mercer 右肩正后方，画面右上前景只有 Wade Mercer 的后脑右侧、右肩和上背，金棕色短发与深酒红色 Polo 衫肩部强烈失焦虚化，占画面不超过四分之一；Wade Mercer 的脸完全不在画框内，全程不转头、不回头、不侧脸，嘴不可见。Cole Mercer 在画面中央近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Cole Mercer［潜水时期］、Wade Mercer（仅肩背前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲过肩反打镜头，近景［越过 Wade Mercer 右肩拍 Cole Mercer 正面］。前景 Wade Mercer 只有后脑、右肩和上背失焦入画，全程背对机位、不转头，只有肩背随呼吸轻微起伏，不开口；Cole Mercer 眼睛一动不动，右臂稳稳箍着怀里的六根金条，胸口慢慢鼓起一口气，随后口型同步开口，音量很低、语速很慢、语气像从牙缝里挤出来地说：（ No thanks to you. ） Cole Mercer说完，嘴唇合上，眼神冷得没有一点温度，仍盯着 Wade Mercer。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Cole Mercer低沉的回答］

【H3 latent 接入文字】承接上一段：Wade Mercer 在驾驶舱门口面南说话，Cole Mercer 在其正南面北，右臂箍着六根金条，全面罩挂在胸前。0.00–1.00 秒从上一段尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。随后切到反打机位：机位在 Wade Mercer 右肩后方，Wade Mercer 只以肩背前景入画，Cole Mercer 正面入画说话。

【交出状态】Cole Mercer 站在驾驶舱门口正南约一臂远，面北，右臂箍着六根金条贴在胸前，全面罩挂在胸前，嘴唇闭合，眼神冷，盯着 Wade Mercer；Wade Mercer 在舱门口面南，右手按在西侧门框上，前景只露后脑、右肩和上背，背对机位；海风大，浪拍船身。
"""

PROMPT_G = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{COLE.format(n=2)}
{SCENE.format(n=3)}
{GOLD.format(n=4)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：承接上一段尾态。Cole Mercer 站在驾驶舱门口正南约一臂远，身体面北，右臂箍着六根金条贴在胸前，眼神冷；Wade Mercer 站在舱门口，身体面南，右手按在西侧门框上。机位在 Cole Mercer 右肩正后方，画面右下前景是 Cole Mercer 的后脑右侧、右肩和上背，强烈失焦虚化；Cole Mercer 怀里的金条在前景下缘只露出一排暗金色的顶端，Cole Mercer 的脸完全不在画框内，全程不转头、不回头、不侧脸，嘴不可见。Wade Mercer 在画面中央中近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Wade Mercer、Cole Mercer［潜水时期］（仅肩背前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲过肩镜头，中近景［越过 Cole Mercer 右肩拍 Wade Mercer 正面］。前景 Cole Mercer 只有后脑、右肩和上背失焦入画，怀里的金条在前景下缘露出一排暗金色顶端，Cole Mercer 背对机位、不转头、不开口；Wade Mercer 的视线越过 Cole Mercer 的肩，直直落到前景下缘的金条上，瞳孔收紧，左手向南伸出、掌心朝上悬在半空，随后口型同步开口，音量短促、语速很快、语气不耐地说：（ Enough. Where's the gold? ） Wade Mercer说完，嘴唇合上，伸出的手掌还悬在半空，目光仍钉在金条上。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Wade Mercer短促的催问］

【H3 latent 接入文字】承接上一段：Cole Mercer 在驾驶舱门口正南面北，右臂箍着六根金条，眼神冷；Wade Mercer 在舱门口面南。0.00–1.00 秒从上一段尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。随后切到机位在 Cole Mercer 右肩后方的过肩镜，Cole Mercer 只以肩背前景入画，Wade Mercer 正面入画说话。

【交出状态】Wade Mercer 站在舱门口面南，左手向南伸出、掌心朝上悬在半空，嘴唇闭合，目光钉在 Cole Mercer 怀里的金条上，右手仍按着西侧门框；Cole Mercer 在其正南面北，右臂箍着六根金条，前景只露后脑、右肩和上背，背对机位；海风大，浪拍船身。
"""

PROMPT_H = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{COLE.format(n=2)}
{SCENE.format(n=3)}
{GOLD.format(n=4)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：承接上一段尾态。Wade Mercer 站在舱门口面南，左手向南伸出悬在半空，右手按着西侧门框；Cole Mercer 站在其正南面北，右臂箍着六根金条。低机位贴着两人脚下的湿甲板、朝北拍：Cole Mercer 只以潜水服的腰腹以下和双臂下缘入画，脸完全不在画框内；金条落尽后机位缓缓上抬到 Wade Mercer 中近景，Wade Mercer 脸和嘴清楚可见，Cole Mercer 退到画外。

【画面内容】
场景：渔船甲板
人物：Wade Mercer、Cole Mercer［潜水时期］（仅腰腹以下与手臂）
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲低机位转上抬镜头，近景转中近景［甲板金条落点转 Wade Mercer 正面］。开头 Cole Mercer 松开箍紧的右臂，六根金条叮叮当当砸在湿漉漉的甲板上滚开，其中一根滚到 Wade Mercer 的船鞋鞋尖前停住（此段 Cole Mercer 只有腰腹以下和手臂入画，脸不入画、不开口）；Wade Mercer 弯腰用左手拾起鞋尖前那根金条，凑到嘴边用门牙咬了一下，又在左手掌心掂了掂分量，嘴角咧开，随后口型同步开口，音量适中、语速偏快、语气像在发号施令地说：（ Real gold. Test it ashore. Give it here. ） Wade Mercer说完，嘴唇合上，右手离开门框，掌心朝上朝西侧甲板上散落的金条摊开。

音频：环境音［海风声、浪拍船身的闷响］+ 动作音［金条砸在甲板上的叮当声、金条滚动声、牙齿咬金属的轻响］+ 人物音［Wade Mercer发号施令的话］

【H3 latent 接入文字】承接上一段：Wade Mercer 在舱门口面南，左手伸向 Cole Mercer 怀里的金条；Cole Mercer 在其正南面北箍着金条。0.00–1.00 秒从上一段尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。随后切到贴甲板的低机位，金条落地，机位上抬到 Wade Mercer 正面。

【交出状态】Wade Mercer 站在舱门口面南，左手托着一根金条停在胸前，右手掌心朝上伸向西南的甲板，嘴唇闭合，嘴角咧着；另外五根金条散在 Cole Mercer 脚边和两人西侧的湿甲板上；Cole Mercer 在画外南侧；海风大，浪拍船身。
"""

PROMPT_G2 = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{COLE.format(n=2)}
{SCENE.format(n=3)}
{GOLD.format(n=4)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：Cole Mercer 站在驾驶舱门口正南约一臂远，身体面北，右臂箍着六根金条贴在胸前，眼神冷；Wade Mercer 站在舱门口，身体面南，右手按在西侧门框上。机位在 Cole Mercer 右肩正后方，画面右下前景是 Cole Mercer 的后脑右侧、右肩和上背，强烈失焦虚化；Cole Mercer 怀里的金条在前景下缘只露出一排暗金色的顶端，Cole Mercer 的脸完全不在画框内，全程不转头、不回头、不侧脸，嘴不可见，画面里只有这一个 Cole Mercer，不在其他位置重复出现。Wade Mercer 在画面中央中近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Wade Mercer、Cole Mercer［潜水时期］（仅肩背前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲过肩镜头，中近景［越过 Cole Mercer 右肩拍 Wade Mercer 正面］。前景 Cole Mercer 只有后脑、右肩和上背失焦入画，怀里的金条在前景下缘露出一排暗金色顶端，Cole Mercer 背对机位、不转头、不开口；Wade Mercer 的视线越过 Cole Mercer 的肩，直直落到前景下缘的金条上，瞳孔收紧，左手向南伸出、掌心朝上悬在半空，随后口型同步开口，音量短促、语速很快、语气不耐地说：（ Enough. Where's the gold? ） Wade Mercer说完，嘴唇合上，伸出的手掌还悬在半空，目光仍钉在金条上。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Wade Mercer短促的催问］

【交出状态】Wade Mercer 站在舱门口面南，左手向南伸出、掌心朝上悬在半空，嘴唇闭合，目光钉在 Cole Mercer 怀里的金条上，右手仍按着西侧门框；Cole Mercer 在其正南面北，右臂箍着六根金条，前景只露后脑、右肩和上背，背对机位；海风大，浪拍船身。
"""

PROMPT_G3 = f"""【H3 提示词】

【参考设定】
{WADE.format(n=1)}
{COLE.format(n=2)}
{SCENE.format(n=3)}
{GOLD.format(n=4)}

{MOOD}

{RULES}

【空间／朝向硬锁】0 秒：Wade Mercer 站在驾驶舱门口，身体面南，右手按在西侧门框上，左手垂在身侧。Wade Mercer 身后只有空的舱门和甲板，不站任何人。画面右下前景只有 Cole Mercer 的后脑一角、右肩和抱着金条的右臂下缘，强烈失焦虚化：金条在他臂弯里只露出一排暗金色的顶端，Cole Mercer 的身体其余部分都在画框外，脸完全不在画框内，全程不转头、不回头、不侧脸，嘴不可见；画面里只有这一个 Cole Mercer 的局部，不出现他的全身或第二张脸。Wade Mercer 在画面中央中近景，焦点清晰，脸和嘴清楚可见。

【画面内容】
场景：渔船甲板
人物：Wade Mercer、Cole Mercer［潜水时期］（仅肩背与手臂前景）
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲过肩镜头，中近景［越过 Cole Mercer 右肩拍 Wade Mercer 正面］。前景 Cole Mercer 只有后脑一角、右肩和抱金条的手臂下缘失焦入画，不转头、不开口，Wade Mercer 身后再无别人；Wade Mercer 的视线越过 Cole Mercer 的肩，直直落到前景下缘的金条上，瞳孔收紧，左手向南伸出、掌心朝上悬在半空，随后口型同步开口，音量短促、语速很快、语气不耐地说：（ Enough. Where's the gold? ） Wade Mercer说完，嘴唇合上，伸出的手掌还悬在半空，目光仍钉在金条上。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Wade Mercer短促的催问］

【交出状态】Wade Mercer 站在舱门口面南，左手向南伸出、掌心朝上悬在半空，嘴唇闭合，目光钉在 Cole Mercer 怀里的金条上，右手仍按着西侧门框，身后舱门和甲板空无一人；Cole Mercer 只以前景的后脑一角、右肩和抱金条的手臂入画，背对机位；海风大，浪拍船身。
"""

PROMPT_PROD3 = f"""【H3 提示词】

【参考设定】
{COLE.format(n=1)}
{WADE.format(n=2)}
{SCENE.format(n=3)}
{MASK.format(n=4)}
{GOLD.format(n=5)}
{TANK.format(n=6)}

{MOOD}

{RULES}
本条共三个镜头，镜头之间硬切。每个镜头里只有点名的说话人正脸入画说话；另一人只以前景碎片（后脑一角、肩背、手臂）入画，脸和嘴完全不在画框内，不转头、不回头。画面里每个人只出现一次，不出现分身或重复人物。

【空间／朝向硬锁】0 秒：承接 U03 尾态。Cole Mercer 站在驾驶舱门口正南约半臂远，身体面北，右臂箍着六根金条贴在胸前，全面罩挂在胸前，气瓶背在背上；Wade Mercer 站在舱门口，身体面南，右手按在西侧门框上。两人南北对峙，Cole 在南、Wade 在北，全条不换位。

【画面内容】
场景：渔船甲板
人物：Cole Mercer［潜水时期］、Wade Mercer
环境描述：白天，阴天，低云压着铁灰色的海面，海风很大，天色发暗

▲镜头一（0–5 秒），过肩镜头，中近景［越过 Cole Mercer 右肩拍 Wade Mercer 正面］。前景只有 Cole Mercer 的后脑一角、右肩和上背失焦入画，他身体其余部分在画框外，脸和嘴不可见、不开口；Wade Mercer 在画面中央，喉头滚了一下，嘴角扯出一点硬邦邦的弧度，口型同步开口，音量适中、语速平稳、语气带着自以为占理的轻慢地说：（ You're alive, aren't you? ） Wade Mercer说完，嘴唇合上，那点弧度还挂在嘴角。
▲镜头二（5–10 秒），过肩反打镜头，近景［越过 Wade Mercer 左肩拍 Cole Mercer 正面］。硬切。前景只有 Wade Mercer 的后脑一角、左肩和上背失焦入画，他身体其余部分在画框外，脸和嘴不可见、不开口；Cole Mercer 在画面中央，右臂稳稳箍着怀里的六根金条，眼睛一动不动，胸口慢慢鼓起一口气，口型同步开口，音量很低、语速很慢、语气像从牙缝里挤出来地说：（ No thanks to you. ） Cole Mercer说完，嘴唇合上，眼神冷得没有一点温度。
▲镜头三（10–15 秒），过肩镜头，中近景［越过 Cole Mercer 右肩拍 Wade Mercer 正面］。硬切。前景只有 Cole Mercer 的后脑一角、右肩和抱着金条的右臂下缘失焦入画，金条在他臂弯里只露出一排暗金色的顶端，他的脸和嘴不可见、不开口，Wade Mercer 身后是空的舱门和甲板，不站任何人；Wade Mercer 在画面中央，视线越过 Cole Mercer 的肩落到前景下缘的金条上，瞳孔收紧，左手向南伸出、掌心朝上悬在半空，口型同步开口，音量短促、语速很快、语气不耐地说：（ Enough. Where's the gold? ） Wade Mercer说完，嘴唇合上，伸出的手掌还悬在半空，目光仍钉在金条上。

音频：环境音［海风声、浪拍船身的闷响］+ 人物音［Wade Mercer轻慢的反问、Cole Mercer低沉的回答、Wade Mercer短促的催问］

【H3 latent 接入文字】承接 U03：Cole 站在驾驶舱门口正南约半臂远的甲板中线上，面北，右臂箍着六根金条贴在湿透的胸口，左手垂着，全面罩挂在胸前，眼神沉着，盯着 Wade；Wade 在舱门口面南，右手按在西侧门框上，下巴绷紧，胸口起伏。0.00–1.00 秒从 U03 尾部最后 1 秒真实原始 H3 AV latent 重生成，保留 24 帧重叠，不自动裁切、合片或淡化；首秒保持人物身份、服装、站位、朝向、视线、持物和现场光声。之后进入本条镜头一。

【交出状态】Wade Mercer 站在舱门口面南，左手向南伸出、掌心朝上悬在半空，嘴唇闭合，目光钉在 Cole Mercer 怀里的金条上，右手仍按着西侧门框；Cole Mercer 在其正南面北，右臂箍着六根金条贴在胸前，全面罩挂在胸前，嘴唇闭合，眼神冷；海风大，浪拍船身，发动机低速运转。
"""

# tag -> (source unit, kept ref indexes in source order, prompt, length,
#         seed, mode)  mode: indep | chain-prod | chain-probe | chain-b1r
#         | chain-pc | chain-pf | chain-pg
PROBES = {
    "P-A-U04L1": ("EP02-U04", [1, 2, 4], PROMPT_A, 120, 3091999188883044845, "indep"),
    "P-B1-U06L1": ("EP01-U06", [0, 1, 3, 4, 5, 6], PROMPT_B1, 144, 6632933335260644632, "chain-prod"),
    "P-B2-U06L2": ("EP01-U06", [2, 3, 6], PROMPT_B2, 168, 6632933335260644632, "chain-probe"),
    "P-C-U04L1-OTS": ("EP02-U04", [1, 0, 2, 4], PROMPT_C, 120, 3091999188883044845, "indep"),
    "P-B1R-U06L1": ("EP01-U06", [0, 3, 4, 5, 6], PROMPT_B1R, 144, 6632933335260644632, "chain-prod"),
    "P-E-U06L1-OTS": ("EP01-U06", [0, 2, 3, 4, 5, 6], PROMPT_E, 144, 6632933335260644632, "chain-prod"),
    "P-D-U06L2-OTS": ("EP01-U06", [2, 0, 3, 6], PROMPT_D, 168, 6632933335260644632, "chain-b1r"),
    "P-F-U04L2-OTS": ("EP02-U04", [0, 1, 2, 3, 4, 5], PROMPT_F, 120, 3091999188883044845, "chain-pc"),
    "P-G-U04L3-OTS": ("EP02-U04", [1, 0, 2, 4], PROMPT_G, 120, 3091999188883044845, "chain-pf"),
    "P-H-U04L4": ("EP02-U04", [1, 0, 2, 4], PROMPT_H, 168, 3091999188883044845, "chain-pg"),
    "P-G2-U04L3-OTS-INDEP": ("EP02-U04", [1, 0, 2, 4], PROMPT_G2, 120, 3091999188883044845, "indep"),
    "P-G3-U04L3-FRAG": ("EP02-U04", [1, 0, 2, 4], PROMPT_G3, 120, 3091999188883044845, "indep"),
    "PROD3-U04-3SHOT": ("EP02-U04", [0, 1, 2, 3, 4, 5], PROMPT_PROD3, 360, 3091999188883044845, "chain-prod"),
}
SAVE_PREFIX = {
    "P-A-U04L1": "h3_context/probe/ep02_u04a",
    "P-B1-U06L1": "h3_context/probe/ep01_u06a",
    "P-B2-U06L2": "h3_context/probe/ep01_u06b",
    "P-C-U04L1-OTS": "h3_context/probe/ep02_u04a_ots",
    "P-B1R-U06L1": "h3_context/probe/ep01_u06a_r",
    "P-E-U06L1-OTS": "h3_context/probe/ep01_u06a_ots",
    "P-D-U06L2-OTS": "h3_context/probe/ep01_u06b_ots",
    "P-F-U04L2-OTS": "h3_context/probe/ep02_u04b_ots",
    "P-G-U04L3-OTS": "h3_context/probe/ep02_u04c_ots",
    "P-H-U04L4": "h3_context/probe/ep02_u04d",
    "P-G2-U04L3-OTS-INDEP": "h3_context/probe/ep02_u04c_ots2",
    "P-G3-U04L3-FRAG": "h3_context/probe/ep02_u04c_frag",
    "PROD3-U04-3SHOT": "h3_context/probe/ep02_u04_3shot",
}


def build(tag: str, spec) -> dict:
    src_tag, keep_idx, prompt, length, seed, mode = spec
    units = {u["tag"]: u for u in json.loads((SRC / "units.json").read_text())["units"]}
    u = units[src_tag]
    wf = json.loads((SRC / u["workflow"]).read_text())

    ins265 = wf["265"]["inputs"]
    ref_keys = sorted(k for k in ins265 if k.startswith("ref_images."))
    keep_nodes = []
    for i in keep_idx:
        keep_nodes.append(ins265[ref_keys[i]][0])
    for k in ref_keys:
        del ins265[k]
    for j, nid in enumerate(keep_nodes):
        ins265[f"ref_images.ref_image_{j}"] = [nid, 0]
    kept_node_ids = set(keep_nodes)
    # drop LoadImage nodes that fed removed refs
    all_ref_nodes = set()
    src_ins = json.loads((SRC / u["workflow"]).read_text())["265"]["inputs"]
    for k in ref_keys:
        all_ref_nodes.add(src_ins[k][0])
    for nid in all_ref_nodes - kept_node_ids:
        wf.pop(nid, None)
    ins265["length"] = length

    swapped = 0
    for node in wf.values():
        ins = node.get("inputs") or {}
        for k, v in list(ins.items()):
            if isinstance(v, str) and v.startswith("【H3 提示词】"):
                ins[k] = prompt
                swapped += 1
            if node.get("class_type") == "SelfLiftH3Sampler" and k == "seed":
                ins[k] = seed
    assert swapped == 2, (tag, swapped)

    if mode == "indep":
        wf["397"]["inputs"]["positive"] = ["265", 0]
        wf["364"]["inputs"]["images"] = ["253", 0]
        wf["364"]["inputs"]["audio"] = ["254", 0]
        for nid in ("9101", "9102", "9103"):
            wf.pop(nid, None)
    elif mode == "chain-probe":
        wf["9101"]["inputs"]["latent_path"] = "h3_context/probe/ep01_u06a_00001.safetensors"
        wf["9101"]["inputs"]["clip_index"] = 1
    elif mode == "chain-b1r":
        wf["9101"]["inputs"]["latent_path"] = "h3_context/probe/ep01_u06a_r_00001.safetensors"
        wf["9101"]["inputs"]["clip_index"] = 1
    elif mode == "chain-pc":
        wf["9101"]["inputs"]["latent_path"] = "h3_context/probe/ep02_u04a_ots_00001.safetensors"
        wf["9101"]["inputs"]["clip_index"] = 1
    elif mode == "chain-pf":
        wf["9101"]["inputs"]["latent_path"] = "h3_context/probe/ep02_u04b_ots_00001.safetensors"
        wf["9101"]["inputs"]["clip_index"] = 1
    elif mode == "chain-pg":
        wf["9101"]["inputs"]["latent_path"] = "h3_context/probe/ep02_u04c_ots_00001.safetensors"
        wf["9101"]["inputs"]["clip_index"] = 1
    # chain-prod keeps the production parent latent wiring untouched

    for node in wf.values():
        if node.get("class_type") == "MiniMaxH3MotionContextSaveLatent":
            node["inputs"]["filename_prefix"] = SAVE_PREFIX[tag]
            node["inputs"]["clip_index"] = 1
    wf["364"]["inputs"]["filename_prefix"] = tag

    keep = {}
    for nid, node in wf.items():
        ct = node.get("class_type")
        ins = node.get("inputs") or {}
        if ct == "LoadAudio" and ins.get("audio") in (None, "None", ""):
            continue
        if ct == "VHS_LoadVideo" and not ins.get("video"):
            continue
        if ct == "LoadImage" and ins.get("image") in (None, "None", ""):
            continue
        keep[nid] = node
    return keep


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    units = {u["tag"]: u for u in json.loads((SRC / "units.json").read_text())["units"]}
    manifest = {}
    for tag, spec in PROBES.items():
        wf = build(tag, spec)
        (DST / f"{tag}.json").write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
        (DST / f"{tag}.txt").write_text(spec[2], encoding="utf-8")
        src_u = units[spec[0]]
        manifest[tag] = {
            "source_unit": spec[0], "length": spec[3], "seed": spec[4],
            "mode": spec[5], "save_prefix": SAVE_PREFIX[tag],
            "assets": [src_u["assets"][i] for i in spec[1]],
        }
        print("built", tag, "refs", len(spec[1]), "length", spec[3], "mode", spec[5])
    (DST / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
