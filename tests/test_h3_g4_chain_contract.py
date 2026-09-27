import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from h3_g4_chain_contract import validate_graph, validate_job


PARENT = "h3_context/ep04_u02_g4_u02_00002.safetensors"


def graph() -> dict:
    return {
        "58": {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
               "inputs": {"model": ["192", 0]}},
        "128": {"inputs": {"model": ["58", 0]}},
        "289": {"inputs": {"step": 12}},
        "264": {"inputs": {"frame_rate": 24}},
        "401": {"class_type": "MiniMaxH3MotionContextLoadLatent",
                "inputs": {"latent_path": PARENT, "clip_index": 2}},
        "400": {"class_type": "MiniMaxH3MotionContextSaveLatent",
                "inputs": {"filename_prefix": "h3_context/ep04_u03", "clip_index": 3}},
    }


def test_frozen_graph_accepts_u03_one_pass() -> None:
    validate_graph(graph(), "U03", PARENT)


@pytest.mark.parametrize("node,key,value", [
    ("289", "step", 10),
    ("264", "frame_rate", 30),
    ("401", "latent_path", "wrong.safetensors"),
    ("400", "clip_index", 2),
])
def test_frozen_graph_rejects_profile_or_parent_change(node: str, key: str,
                                                        value: object) -> None:
    changed = copy.deepcopy(graph())
    changed[node]["inputs"][key] = value
    with pytest.raises(RuntimeError, match="graph changed"):
        validate_graph(changed, "U03", PARENT)


def test_job_parent_chain_must_match_unit() -> None:
    job = {"unit_id": "U03", "parent_unit_id": "U02", "template": "yz_h3_ep_unit",
           "fields": {"filename_prefix": "EP04-U03-v16"}}
    validate_job(job, "U03")
    job["parent_unit_id"] = "U01"
    with pytest.raises(RuntimeError, match="job contract mismatch"):
        validate_job(job, "U03")
