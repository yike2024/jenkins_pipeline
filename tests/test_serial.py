import pytest
from conftest import run_cmd

# (用例名, 命令, 期望字符串, 超时秒)
TESTS = [
    ('系统信息', 'cat /etc/os-release', 'PRETTY_NAME', 5),
    ('BM版本',   'bm_version',          'SophonSDK',   5),
    # 在这里继续加用例
]


@pytest.mark.parametrize('name,cmd,expect,timeout', TESTS,
                         ids=[t[0] for t in TESTS])
def test_board_cmd(board, name, cmd, expect, timeout):
    ok, out = run_cmd(board, cmd, expect, timeout=timeout)
    print(f'\n$ {cmd}\n{out}')          # 输出会附在失败报告里
    assert ok, f'[{name}] 未等到期望输出: {expect}'

