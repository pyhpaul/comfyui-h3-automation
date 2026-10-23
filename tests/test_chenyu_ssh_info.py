"""Parse Chenyu SSH login panels without talking to CDP."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ops"))
from chenyu_ssh_info import list_running_ids, parse_ssh_block


SAMPLE = """
实例ID：
b5ef7a838b2d40c8a24c7b7da143f6f7
SSH
SSH 登录信息
连接主机：
b5ef7a838b2d40c8a24c7b7da143f6f771.gz14.chenyu.cn
端口：
29679
用户：
root
密码：
secret-pass-12
连接命令：
ssh root@b5ef7a838b2d40c8a24c7b7da143f6f771.gz14.chenyu.cn -p 29679
运行状态：
运行中
"""


PAGE = """
实例ID：
b5ef7a838b2d40c8a24c7b7da143f6f7
运行状态：
运行中
实例ID：
ee58bde62caf457e810680ba64e7cbe5
运行状态：
已关机
"""


def test_parse_ssh_block_reads_host_port_password():
    info = parse_ssh_block(SAMPLE)
    assert info is not None
    assert info["host"] == "b5ef7a838b2d40c8a24c7b7da143f6f771.gz14.chenyu.cn"
    assert info["port"] == "29679"
    assert info["user"] == "root"
    assert info["password"] == "secret-pass-12"
    assert info["cmd"].startswith("ssh root@")


def test_parse_ssh_block_returns_none_without_panel():
    assert parse_ssh_block("运行状态：\n运行中\n") is None


def test_list_running_ids_skips_powered_off_cards():
    assert list_running_ids(PAGE) == ["b5ef7a838b2d40c8a24c7b7da143f6f7"]
