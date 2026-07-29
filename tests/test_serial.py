import pytest
from conftest import run_cmd, REMOTE_TEST_ROOT

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


def test_prepare_athena2_env(board):
    ok, out = run_cmd(
        board,
        f'test -d {REMOTE_TEST_ROOT} && ls {REMOTE_TEST_ROOT}/requirements.txt && echo CHECK_DIR_OK',
        'CHECK_DIR_OK',
        timeout=10,
        quiet=0.5,
        own_line=True,
    )
    assert ok, f'板子上缺少测试目录或 requirements.txt: {REMOTE_TEST_ROOT}\n{out}'

    ok, out = run_cmd(
        board,
        'test -d /data/utils && ls /data/utils/file_op.py && echo CHECK_UTILS_OK',
        'CHECK_UTILS_OK',
        timeout=10,
        quiet=0.5,
        own_line=True,
    )
    assert ok, (
        '板子上缺少 /data/utils。请把仓库 pytest/utils 目录拷到 /data/utils '
        f'(与 athena2_daily_test 同级)\n{out}'
    )

    ok, out = run_cmd(
        board,
        f'cd {REMOTE_TEST_ROOT} && python3 -m pip install -r requirements.txt ; echo PIP_INSTALL_DONE',
        'PIP_INSTALL_DONE',
        timeout=600,
        quiet=1,
        own_line=True,
    )
    assert ok, f'pip install -r requirements.txt 超时或失败\n{out}'

    ok, out = run_cmd(
        board,
        'PYTHONPATH=/data:$PYTHONPATH python3 -c "from utils.file_op import change_dir; import pytest; print(pytest.__version__)" ; echo CHECK_PYTEST_OK',
        'CHECK_PYTEST_OK',
        timeout=20,
        quiet=0.5,
        own_line=True,
    )
    assert ok and 'No module named' not in out, f'安装后仍无法 import pytest/utils\n{out}'
    print('\nathena2 环境准备完成', flush=True)
