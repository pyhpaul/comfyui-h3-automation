"""The Chenyu console id is shorter than the SSH hostname."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from chenyu_shutdown import instance_matches, is_confirm_label, page_instance_id


PAGE = "实例ID：\nee58bde62caf457e810680ba64e7cbe5 \n自定名称"
HOST = "ee58bde62caf457e810680ba64e7cbe571.gz15.chenyu.cn"


def test_page_id_matches_ssh_host_without_the_short_suffix():
    assert page_instance_id(PAGE) == "ee58bde62caf457e810680ba64e7cbe5"
    assert instance_matches(PAGE, HOST)


def test_exact_label_also_matches():
    assert instance_matches("实例ID：ee58bde62caf457e810680ba64e7cbe571", HOST)


def test_different_instance_does_not_match():
    assert not instance_matches("实例ID：aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", HOST)


def test_confirm_button_ignores_the_space_inside_确定():
    assert is_confirm_label("确 定")
    assert not is_confirm_label("取消")
    assert not is_confirm_label("确定关机并销毁")
