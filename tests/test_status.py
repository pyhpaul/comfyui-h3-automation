from comfy_orch.status import JobStatus, write_status, read_status

def test_status_roundtrip(tmp_path):
    p = tmp_path / "runs" / "j1" / "status.json"
    st = JobStatus(job_id="j1", state="pending", prompt_id=None, message="", outputs=[])
    write_status(p, st)
    got = read_status(p)
    assert got.state == "pending"
    assert got.job_id == "j1"
