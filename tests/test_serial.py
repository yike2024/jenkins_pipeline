import pytest
from conftest import run_cmd

TESTS = [
    ('系统信息', 'cat /etc/os-release', 'PRETTY_NAME', 5),
    ('BM版本',   'bm_version',          'SophonSDK',   5),
]


@pytest.mark.parametrize('name,cmd,expect,timeout', TESTS,
                         ids=[t[0] for t in TESTS])
def test_board_cmd(board, name, cmd, expect, timeout):
    ok, out = run_cmd(board, cmd, expect, timeout=timeout)
    assert ok, f'[{name}] 未等到期望输出: {expect}\n实际输出:\n{out}'


def test_board_ip(board_ip):
    assert board_ip, '板子 IP 为空'
    print(f'BOARD_IP={board_ip}', flush=True)
