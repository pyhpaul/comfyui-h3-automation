from comfy_orch.av_review.compact import compact_payload, validate_payload_answer
from comfy_orch.av_review.workorders import constraint_disposition
from comfy_orch.av_review.workorders import constraint_candidates


def work(source):
    return {"unit": "U", "source": {"sha256": "video"}, "prompt_sha256": "prompt",
            "source_expectations": source, "constraint_candidates": constraint_candidates(source),
            "original_claims": [{"id": "S1", "observed": "unchanged"}], "images": []}


def test_literal_projection_preserves_scope_offsets_and_owner_lines():
    source = "【参考设定】\nAva：开衫敞着穿。\n【画面内容】\n▲末镜。Damian在镜头外。\n音频：底噪。"
    original = work(source)
    payload, audit = compact_payload(original)
    assert original["source_expectations"] == source
    for record in payload["source_evidence"]:
        for pos in record["occurrences"]:
            assert source[pos["start"]:pos["end"]] == record["text"]
    assert "Ava：开衫敞着穿。" in [b["text"] for b in payload["source_evidence"]]
    assert payload["original_claims"] == original["original_claims"]
    assert audit["excluded_lines"] and payload["missing_context_action"].startswith("UNVERIFIABLE")


def test_different_sections_or_changed_states_are_not_merged():
    source = "【参考设定】\n开衫敞着穿。\n开衫敞着穿。\n【交出状态】\n开衫敞着穿。\n开衫已扣上。"
    payload, audit = compact_payload(work(source))
    assert audit["included_line_occurrences"] == audit["included_unique_lines"]+1
    records = payload["source_evidence"]
    assert sum(b["text"] == "开衫敞着穿。" for b in records) == 2
    assert any(b["text"] == "开衫已扣上。" for b in records)


def test_quantity_meaning_retained_in_whole_shot_not_inferred_from_old_claim():
    source = "【画面内容】\n▲打开衣柜，里面挂着一件白衬衫。"
    payload, _ = compact_payload(work(source))
    assert payload["source_evidence"][0]["text"] == source.splitlines()[1]
    assert payload["constraint_candidates"] == []


def test_audio_dependent_constraint_is_deferred_not_cleared_or_dropped():
    source = "有台词的镜头里，只有点名的说话人开口，其他人嘴唇闭合。\n▲末镜。Damian在镜头外。"
    original = work(source)
    payload, _ = compact_payload(original)
    assert len(original["constraint_candidates"]) == 2
    assert payload["deferred_constraints"] == [{"id": "C1", "reason": "NO_AUDIO_NOT_CHECKED"}]
    assert payload["constraint_candidates"][0]["id"] == "C2"


def test_deferred_echo_allowed_but_positive_or_invented_constraint_rejected():
    original = work("有台词的镜头里，只有点名的说话人开口，其他人嘴唇闭合。")
    original["original_claims"] = []
    payload, _ = compact_payload(original)
    check = {"id": "C1", "source_quote": "", "status": "NOT_CHECKED", "frame_ids": []}
    answer = {"unit": "U", "audio_status": "AUDIO_UNAVAILABLE", "L2_status": "NOT_DONE",
              "claim_checks": [], "constraint_checks": [check], "new_observations": [], "limitations": []}
    assert not validate_payload_answer(answer, original, payload)
    check["status"] = "POSSIBLE_SOURCE_DEVIATION"
    assert validate_payload_answer(answer, original, payload)
    check.update(id="invented", status="NOT_CHECKED")
    assert validate_payload_answer(answer, original, payload)


def test_out_of_scope_requires_scope_review_never_silent_clearance():
    assert constraint_disposition({"status": "OUT_OF_SCOPE"}) == "SCOPE_REVIEW"
    assert constraint_disposition({"status": "CONSISTENT_IN_STILLS"}) == "PARTIAL_CHECK_NOT_CLEARANCE"


def test_active_constraint_cannot_be_omitted_to_get_a_valid_result():
    original = work("Damian在镜头外。")
    original["original_claims"] = []
    payload, _ = compact_payload(original)
    answer = {"unit": "U", "audio_status": "AUDIO_UNAVAILABLE", "L2_status": "NOT_DONE",
              "claim_checks": [], "constraint_checks": [], "new_observations": [], "limitations": []}
    assert validate_payload_answer(answer, original, payload)
