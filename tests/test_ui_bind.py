from __future__ import annotations

import copy
import json
from pathlib import Path

from comfy_orch.ui_bind import apply_values_to_ui_workflow, export_bound_ui_workflow


def test_apply_values_preserves_layout_and_patches_widgets():
    ui = {
        "last_node_id": 300,
        "nodes": [
            {
                "id": 51,
                "type": "LoadImage",
                "pos": [100, 200],
                "size": [50, 60],
                "widgets_values": ["old.png", "image"],
            },
            {
                "id": 27,
                "type": "VHS_LoadVideo",
                "pos": [1, 2],
                "widgets_values": {"video": "", "format": "AnimateDiff"},
            },
            {
                "id": 263,
                "type": "Text",
                "pos": [3, 4],
                "widgets_values": ["old"],
            },
            {
                "id": 259,
                "type": "PrimitiveFloat",
                "pos": [5, 6],
                "widgets_values": [15],
            },
            {
                "id": 252,
                "type": "ResolutionSelector",
                "pos": [7, 8],
                "widgets_values": ["16:9 (Widescreen)", 0.5, 32],
            },
        ],
        "links": [[1, 51, 0, 5, 0, "IMAGE"]],
        "groups": [{"title": "g"}],
    }
    before = copy.deepcopy(ui)
    out = apply_values_to_ui_workflow(
        ui,
        values={
            "ref_image_0": "control.png",
            "ref_video_0": "previz.webm",
            "prompt": "hello",
            "duration_seconds": 10,
            "aspect_ratio": "9:16 (Portrait Widescreen)",
        },
    )
    by_id = {n["id"]: n for n in out["nodes"]}
    assert by_id[51]["pos"] == [100, 200]
    assert by_id[51]["widgets_values"][0] == "control.png"
    assert by_id[27]["widgets_values"]["video"] == "previz.webm"
    assert by_id[263]["widgets_values"] == ["hello"]
    assert by_id[259]["widgets_values"] == [10]
    assert by_id[252]["widgets_values"][0] == "9:16 (Portrait Widescreen)"
    assert out["links"] == before["links"]
    assert out["groups"] == before["groups"]
    # original untouched
    assert ui["nodes"][0]["widgets_values"][0] == "old.png"


def test_placeholder_audio_mutes_loadaudio_and_disconnects_h3():
    ui = {
        "nodes": [
            {
                "id": 48,
                "type": "LoadAudio",
                "mode": 0,
                "pos": [0, 0],
                "widgets_values": ["None", None, None],
                "outputs": [{"name": "AUDIO", "links": [391]}],
            },
            {
                "id": 14,
                "type": "LoadAudio",
                "mode": 0,
                "widgets_values": ["None", None, None],
                "outputs": [{"name": "AUDIO", "links": [392]}],
            },
            {
                "id": 15,
                "type": "LoadAudio",
                "mode": 0,
                "widgets_values": ["None", None, None],
                "outputs": [{"name": "AUDIO", "links": [393]}],
            },
            {
                "id": 265,
                "type": "MiniMaxH3ReferenceToVideo",
                "inputs": [
                    {"name": "ref_audios.ref_audio_0", "link": 391},
                    {"name": "ref_audios.ref_audio_1", "link": 392},
                    {"name": "ref_audios.ref_audio_2", "link": 393},
                    {"name": "prompt", "link": 399},
                ],
            },
        ],
        "links": [
            [391, 48, 0, 265, 0, "AUDIO"],
            [392, 14, 0, 265, 1, "AUDIO"],
            [393, 15, 0, 265, 2, "AUDIO"],
            [399, 263, 0, 265, 3, "STRING"],
        ],
    }
    out = apply_values_to_ui_workflow(
        ui,
        values={
            "ref_audio_0": "silent_placeholder.wav",
            "ref_audio_1": "silent_placeholder.wav",
            "ref_audio_2": "silent_placeholder.wav",
        },
    )
    by_id = {n["id"]: n for n in out["nodes"]}
    assert by_id[48]["mode"] == 2
    assert by_id[14]["mode"] == 2
    assert by_id[15]["mode"] == 2
    h3_audio = [
        i for i in by_id[265]["inputs"] if i["name"].startswith("ref_audios.")
    ]
    assert all(i["link"] is None for i in h3_audio)
    assert [L[0] for L in out["links"]] == [399]


def test_export_bound_ui_workflow_roundtrip(tmp_path: Path):
    src = tmp_path / "ui.json"
    src.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": 51,
                        "type": "LoadImage",
                        "pos": [0, 0],
                        "widgets_values": ["x", "image"],
                    }
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "bound.json"
    export_bound_ui_workflow(
        ui_workflow_path=src,
        values={"ref_image_0": "a.png"},
        out_path=out,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["nodes"][0]["widgets_values"][0] == "a.png"


def test_mute_unused_image_slots_disconnects_h3():
    ui = {
        "nodes": [
            {
                "id": 51,
                "type": "LoadImage",
                "mode": 0,
                "widgets_values": ["old.png", "image"],
                "outputs": [{"links": [378]}],
            },
            {
                "id": 49,
                "type": "LoadImage",
                "mode": 0,
                "widgets_values": ["old.png", "image"],
                "outputs": [{"links": [379]}],
            },
            {
                "id": 19,
                "type": "LoadImage",
                "mode": 0,
                "widgets_values": ["old.png", "image"],
                "outputs": [{"links": [382]}],
            },
            {
                "id": 265,
                "type": "MiniMaxH3ReferenceToVideo",
                "inputs": [
                    {"name": "ref_images.ref_image_0", "link": 378},
                    {"name": "ref_images.ref_image_1", "link": 379},
                    {"name": "ref_images.ref_image_4", "link": 382},
                ],
            },
        ],
        "links": [
            [378, 51, 0, 265, 0, "IMAGE"],
            [379, 49, 0, 265, 1, "IMAGE"],
            [382, 19, 0, 265, 2, "IMAGE"],
        ],
    }
    out = apply_values_to_ui_workflow(
        ui,
        values={"ref_image_0": "control.png", "ref_image_1": "a.png"},
        disable_placeholder_audio=False,
    )
    by_id = {n["id"]: n for n in out["nodes"]}
    assert by_id[51]["widgets_values"][0] == "control.png"
    assert by_id[49]["widgets_values"][0] == "a.png"
    assert by_id[19]["mode"] == 2
    by_name = {i["name"]: i["link"] for i in by_id[265]["inputs"]}
    assert by_name["ref_images.ref_image_0"] == 378
    assert by_name["ref_images.ref_image_1"] == 379
    assert by_name["ref_images.ref_image_4"] is None
