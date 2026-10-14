"""Evaluate prompt-bound ComfyUI progress_state snapshots without GPU access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SAMPLER_NODE = "226"
SAMPLER_STEPS = tuple(range(1, 13))


@dataclass(frozen=True)
class ProgressEvidence:
    state: str
    reason: str | None
    steps: tuple[int, ...]
    observed_node_interval_s: float | None
    first_received_at_utc: str | None
    last_received_at_utc: str | None


def _unknown(reason: str, steps: list[int]) -> ProgressEvidence:
    return ProgressEvidence("sampler_unknown", reason, tuple(steps), None, None, None)


def _snapshot_node(message: Any, prompt_id: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(message, dict):
        return None, "observer message is malformed"
    if message.get("type") != "progress_state":
        return None, None
    data = message.get("data")
    if not isinstance(data, dict) or data.get("prompt_id") != prompt_id:
        return None, "foreign or malformed progress_state prompt"
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return None, "progress_state has no node map"
    node = nodes.get(SAMPLER_NODE)
    if node is None:
        return None, None
    if not isinstance(node, dict) or node.get("prompt_id") != prompt_id \
            or node.get("node_id") != SAMPLER_NODE:
        return None, "sampler node identity differs"
    return node, None


def evaluate_progress(trace: dict[str, Any], history: dict[str, Any],
                      prompt_id: str) -> ProgressEvidence:
    """Return unknown, never fabricated steps, when the event chain is incomplete."""
    steps: list[int] = []
    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        return _unknown("target history is missing", steps)
    prompt = entry.get("prompt")
    client_id = trace.get("client_id")
    if not isinstance(prompt, list) or len(prompt) < 4 or prompt[1] != prompt_id \
            or not isinstance(prompt[3], dict) or prompt[3].get("client_id") != client_id:
        return _unknown("history client ID does not match observer", steps)
    status = entry.get("status", {})
    if not isinstance(status, dict):
        return _unknown("target history status is malformed", steps)
    if status.get("status_str") != "success" or status.get("completed") is not True:
        return _unknown("target history is not successful", steps)
    messages = status.get("messages", [])
    if not isinstance(messages, list) or any(
            not isinstance(item, (list, tuple)) or len(item) != 2
            or not isinstance(item[1], dict) for item in messages):
        return _unknown("target history messages are malformed", steps)
    if any(data.get("prompt_id") != prompt_id for _, data in messages):
        return _unknown("target history contains foreign prompt messages", steps)
    kinds = [kind for kind, _ in messages]
    if kinds.count("execution_start") != 1 or kinds.count("execution_success") != 1:
        return _unknown("target history execution markers are incomplete", steps)
    cached = [data.get("nodes") for kind, data in messages if kind == "execution_cached"]
    if len(cached) != 1 or not isinstance(cached[0], list) or SAMPLER_NODE in cached[0]:
        return _unknown("sampler cache status is not proven executed", steps)
    events = trace.get("events")
    if not isinstance(events, list) or not events:
        return _unknown("observer trace is empty", steps)
    handshake = events[0].get("message", {}) if isinstance(events[0], dict) else {}
    if not isinstance(handshake, dict) or handshake.get("type") != "status" \
            or not isinstance(handshake.get("data"), dict) \
            or handshake["data"].get("sid") != client_id:
        return _unknown("client ID handshake is missing", steps)
    if trace.get("closed_reason") != "terminal":
        return _unknown("observer did not reach a normal terminal event", steps)
    terminal_indices = [index for index, event in enumerate(events)
                        if isinstance(event, dict)
                        and isinstance(event.get("message"), dict)
                        and event["message"].get("type") == "executing"
                        and isinstance(event["message"].get("data"), dict)
                        and event["message"]["data"].get("prompt_id") == prompt_id
                        and event["message"]["data"].get("node", "missing") is None]
    if len(terminal_indices) != 1:
        return _unknown("target prompt terminal event is missing", steps)
    terminal_index = terminal_indices[0]
    reconciliation = trace.get("reconciliation")
    if reconciliation is not None:
        if not isinstance(reconciliation, dict) \
                or reconciliation.get("method") != "late_prompt_id" \
                or reconciliation.get("terminal_event_index") != terminal_index:
            return _unknown("late prompt ID reconciliation differs", steps)
    elif terminal_index != len(events) - 1:
        return _unknown("target terminal has unreconciled trailing events", steps)

    started = False
    finished = False
    terminal_count = 0
    start_event: dict[str, Any] | None = None
    finish_event: dict[str, Any] | None = None
    previous_ns = -1
    previous_utc: datetime | None = None
    for event in events:
        try:
            received_ns = event["received_monotonic_ns"]
            received_utc = event["received_at_utc"]
            message = event["message"]
            parsed = datetime.fromisoformat(received_utc.replace("Z", "+00:00"))
        except (KeyError, AttributeError, TypeError, ValueError):
            return _unknown("observer event timestamp is invalid", steps)
        if parsed.tzinfo is None:
            return _unknown("observer event timestamp has no timezone", steps)
        if previous_utc is not None and parsed < previous_utc:
            return _unknown("observer UTC time regressed", steps)
        previous_utc = parsed
        if not isinstance(received_ns, int) or received_ns <= previous_ns:
            return _unknown("observer monotonic time did not increase", steps)
        previous_ns = received_ns
        if not isinstance(message, dict):
            return _unknown("observer message is malformed", steps)
        if terminal_count and message.get("type") == "progress_state" \
                and isinstance(message.get("data"), dict) \
                and message["data"].get("prompt_id") == prompt_id:
            return _unknown("target progress continued after terminal", steps)
        if message.get("type") == "executing" and isinstance(message.get("data"), dict) \
                and message["data"].get("prompt_id") == prompt_id \
                and message["data"].get("node", "missing") is None:
            terminal_count += 1
            if terminal_count > 1:
                return _unknown("target terminal event is repeated", steps)
        node, error = _snapshot_node(message, prompt_id)
        if error is not None:
            return _unknown(error, steps)
        if node is None:
            continue
        state = node.get("state")
        value = node.get("value")
        maximum = node.get("max")
        if isinstance(value, bool) or isinstance(maximum, bool) \
                or not isinstance(value, (int, float)) or not isinstance(maximum, (int, float)):
            return _unknown("sampler progress value is not numeric", steps)
        if state == "running" and value == 0 and maximum == 1 and not steps and not finished:
            started = True
            if start_event is None:
                start_event = event
            continue
        if state == "running" and maximum == 12 and started and not finished:
            if isinstance(value, float) and not value.is_integer():
                return _unknown("sampler step is fractional", steps)
            number = int(value)
            if steps and number == steps[-1]:
                continue
            if number != len(steps) + 1 or number > 12:
                return _unknown("sampler step is missing or regressed", steps)
            steps.append(number)
            continue
        if state == "finished" and value == 12 and maximum == 12 \
                and started and steps == list(SAMPLER_STEPS):
            if not finished:
                finished = True
                finish_event = event
            continue
        return _unknown("sampler state or max changed unexpectedly", steps)
    if not started or not finished or terminal_count != 1 \
            or start_event is None or finish_event is None:
        return _unknown("sampler progress did not complete 12 steps", steps)
    interval = (finish_event["received_monotonic_ns"]
                - start_event["received_monotonic_ns"]) / 1_000_000_000
    if interval <= 0:
        return _unknown("observer node interval is invalid", steps)
    return ProgressEvidence("derived_verified", None, tuple(steps), interval,
                            start_event["received_at_utc"], finish_event["received_at_utc"])


def read_trace(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())
