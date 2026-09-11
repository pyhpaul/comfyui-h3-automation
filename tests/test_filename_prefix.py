from __future__ import annotations

from comfy_orch.ep_pack import default_filename_prefix


def test_default_filename_prefix_prefers_ep_unit():
    assert default_filename_prefix("EP01-H3-latent-test-package-v1", "U01") == "EP01-U01"
    assert default_filename_prefix("EP03", "U02") == "EP03-U02"
    assert default_filename_prefix("weird name!", "U01") == "weird-name-U01"
