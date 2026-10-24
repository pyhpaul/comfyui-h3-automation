import pytest

from comfy_orch.av_review.workorders import adaptive_frames, constraint_candidates, followup_disposition, validate_followup


def test_candidates_preserve_exact_source_offsets_and_do_not_invent_exclusivity():
    source = "里面挂着一件白衬衫。Damian在镜头外；Noah的外套已经脱下。只有一个盒子。"
    result = constraint_candidates(source)
    assert len(result) == 3
    assert all(source[c["start"]:c["end"]] == c["quote"] for c in result)
    assert [c["exclusive_word_present"] for c in result] == [False, False, True]
    assert all(c["status"] == "CANDIDATE_NOT_ACCEPTED" for c in result)


def test_risk_selection_is_variable_and_keeps_neighbors_and_deferred():
    frames = [f"F{i:03d}" for i in range(1, 10)]
    claim = {"id": "S1", "category": "anatomy", "frame_ids": ["F005"]}
    result = adaptive_frames([claim], frames, [])
    assert result["selected"] == ["F005", "F004", "F006"]
    result = adaptive_frames([claim], frames, ["F001", "F009"], 3)
    assert result["selected"] == ["F001", "F009", "F005"]
    assert result["deferred"] and result["claim_coverage"][0]["selected_cited_frames"] == ["F005"]


def test_anchor_budget_not_silently_dropped():
    with pytest.raises(ValueError, match="exceed"):
        adaptive_frames([], ["F001", "F002"], ["F001", "F002"], 1)


def fixture():
    workorder = {"unit": "U", "images": [{"frame_id": "F001"}],
                 "original_claims": [{"id": "S1", "observed": "coat on chair"}],
                 "constraint_candidates": [{"id": "C1", "quote": "Damian在镜头外。"}]}
    answer = {"unit": "U", "audio_status": "AUDIO_UNAVAILABLE", "L2_status": "NOT_DONE",
              "claim_checks": [{"id": "S1", "status": "UNVERIFIABLE", "issue_class": "INSUFFICIENT_EVIDENCE",
                                "frame_ids": [], "reason": "Hidden"}],
              "constraint_checks": [], "new_observations": [], "limitations": []}
    return workorder, answer


def test_missing_original_claim_is_not_clearance():
    workorder, answer = fixture()
    assert not validate_followup(answer, workorder)
    answer["claim_checks"] = []
    assert validate_followup(answer, workorder)


def test_unknown_frame_and_altered_quote_are_rejected():
    workorder, answer = fixture()
    answer["constraint_checks"] = [{"id": "C1", "source_quote": "Only Damian is visible",
                                    "frame_ids": ["F002"], "status": "POSSIBLE_SOURCE_DEVIATION"}]
    assert len(validate_followup(answer, workorder)) == 2


def test_supported_claim_needs_evidence_not_status_string():
    workorder, answer = fixture()
    answer["claim_checks"][0]["status"] = "SUPPORTED_STILL_SUSPECT"
    assert validate_followup(answer, workorder)


@pytest.mark.parametrize("value", [None, "not a list", 1, [{"id": {"invalid": "type"}}]])
def test_malformed_constraints_fail_closed_without_crashing(value):
    workorder, answer = fixture()
    answer["constraint_checks"] = value
    assert validate_followup(answer, workorder)


def test_selection_preserves_original_claims_and_exposes_unread_evidence():
    claim = {"id": "S1", "category": "prop_continuity", "observed": "coat on chair",
             "frame_ids": ["F002", "F005"], "detail_frame_ids": ["F005"]}
    original = dict(claim)
    result = adaptive_frames([claim], [f"F{i:03d}" for i in range(1, 7)], [], 2)
    assert claim == original
    assert result["selected"] == ["F005", "F004"]
    assert "F002" in result["claim_coverage"][0]["unselected_cited_frames"]


def test_invalid_status_type_is_reported_not_accepted():
    workorder, answer = fixture()
    answer["claim_checks"][0]["status"] = []
    assert validate_followup(answer, workorder)


@pytest.mark.parametrize("status,category,expected", [
    ("SUPPORTED_STILL_SUSPECT", "INSUFFICIENT_EVIDENCE", "NEEDS_EVIDENCE"),
    ("SUPPORTED_STILL_SUSPECT", "SOURCE_DEVIATION", "DIRECTOR_REVIEW"),
    ("SUPPORTED_STILL_SUSPECT", "VISUAL_ANOMALY", "VISUAL_REVIEW"),
    ("UNVERIFIABLE", "VISUAL_ANOMALY", "NEEDS_EVIDENCE"),
    ("NOT_SUPPORTED_IN_SELECTED_STILLS", "SOURCE_DEVIATION", "WITHDRAW_ORIGINAL_ONLY"),
    ("INVALID_EXPECTATION", "SOURCE_DEVIATION", "REJECT_EXPECTATION"),
])
def test_queue_does_not_mistake_supported_label_for_a_defect(status, category, expected):
    assert followup_disposition({"status": status, "issue_class": category}) == expected
