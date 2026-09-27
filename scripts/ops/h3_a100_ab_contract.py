"""Pure validation rules for the controlled A100 H3 attention comparison."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any


RUN_PROFILES = {
    "P_B": "rtx4080",
    "P_C": "a100_sage_sm80",
    "B1": "rtx4080",
    "C1": "a100_sage_sm80",
    "B2": "rtx4080",
    "C2": "a100_sage_sm80",
    "S0": "a100_sage_sm80",
    "M0": "a100_sage_sm80",
    "S1": "a100_sage_sm80",
    "M1": "a100_sage_sm80",
    "S2": "a100_sage_sm80",
    "M2": "a100_sage_sm80",
}
MEMORY_FORMAL_RUNS = ("S1", "M1", "S2", "M2")
FORMAL_RUNS = ("B1", "C1", "B2", "C2", *MEMORY_FORMAL_RUNS)
PREWARM_RUNS = ("P_B", "P_C", "S0", "M0")
STEP_COUNT = 12
_STEP_RE = re.compile(r"(?<!\d)(\d+)/12 \[(\d+):(\d{2})<")


@dataclass(frozen=True)
class StepTiming:
    elapsed_seconds: tuple[int, ...]
    intervals_seconds: tuple[int, ...]


def normalized_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Ignore only the reviewed attention edge and per-run output prefixes."""
    out = copy.deepcopy(graph)
    if not {"128", "264", "400"}.issubset(out):
        raise ValueError("required H3 graph nodes are missing")
    if "58" in out:
        node = out["58"]
        if (node.get("class_type") != "MiniMaxH3MemoryEfficientSageAttentionPatch"
                or node.get("inputs") != {"model": ["192", 0]}
                or out["128"]["inputs"].get("model") != ["58", 0]):
            raise ValueError("unexpected candidate attention node or edge")
    elif out["128"]["inputs"].get("model") != ["192", 0]:
        raise ValueError("unexpected bypass attention edge")
    out.pop("58", None)
    out["128"]["inputs"]["model"] = ["ATTENTION_CANDIDATE", 0]
    for node in ("264", "400"):
        out[node]["inputs"]["filename_prefix"] = "RUN_PREFIX"
    return out


def graphs_match_except_candidate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return normalized_graph(left) == normalized_graph(right)


def graphs_match_except_output_prefix(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """For a runtime-flag trial, attention and every other graph edge must match."""
    copies = (copy.deepcopy(left), copy.deepcopy(right))
    for graph in copies:
        if not {"264", "400"}.issubset(graph):
            raise ValueError("required H3 output nodes are missing")
        for node in ("264", "400"):
            graph[node]["inputs"]["filename_prefix"] = "RUN_PREFIX"
    return copies[0] == copies[1]


def warmup_graphs_match_except_latent_prefix(left: dict[str, Any], right: dict[str, Any]) -> bool:
    copies = (copy.deepcopy(left), copy.deepcopy(right))
    for graph in copies:
        if ("400" not in graph or "264" in graph
                or graph.get("289", {}).get("inputs", {}).get("step") != 1):
            raise ValueError("expected one-step H3 graph without the MP4 output node")
        graph["400"]["inputs"]["filename_prefix"] = "RUN_PREFIX"
    return copies[0] == copies[1]


def parse_step_timing(log: str) -> StepTiming:
    """Extract each completed tqdm step from the ComfyUI CR-delimited log."""
    elapsed: dict[int, int] = {}
    for match in _STEP_RE.finditer(log):
        step, minutes, seconds = (int(part) for part in match.groups())
        if 1 <= step <= STEP_COUNT:
            elapsed.setdefault(step, minutes * 60 + seconds)
    if set(elapsed) != set(range(1, STEP_COUNT + 1)):
        raise ValueError(f"expected 12 completed sampler steps, found {sorted(elapsed)}")
    ordered = tuple(elapsed[step] for step in range(1, STEP_COUNT + 1))
    if any(later <= earlier for earlier, later in zip(ordered, ordered[1:])):
        raise ValueError("sampler step times are not increasing")
    return StepTiming(ordered, tuple(later - earlier for earlier, later in zip(ordered, ordered[1:])))


def improvement_fraction(baseline_seconds: float, candidate_seconds: float) -> float:
    if baseline_seconds <= 0 or candidate_seconds <= 0:
        raise ValueError("timing values must be positive")
    return (baseline_seconds - candidate_seconds) / baseline_seconds


def timing_pair_passes(baseline: dict[str, float], candidate: dict[str, float]) -> bool:
    return all(improvement_fraction(baseline[key], candidate[key]) >= 0.15
               for key in ("server_wall_s", "sampler_wall_s"))
