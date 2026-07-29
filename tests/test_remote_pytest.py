import os
import re
import time
import subprocess
import xml.etree.ElementTree as ET
import pytest
from conftest import run_cmd, PROMPT, REMOTE_JPEG_DIR

REMOTE_TEST_DIR = REMOTE_JPEG_DIR
REMOTE_XML = '/tmp/jpeg_results.xml'
LOCAL_XML = os.path.join(os.path.dirname(__file__), '..', 'remote_jpeg_results.xml')
BOARD_USER = os.environ.get('BOARD_USER', 'linaro')
BOARD_SSH_PASS = os.environ.get('BOARD_SSH_PASS', 'linaro')

PYTEST_TIMEOUT = 1800
SCP_TIMEOUT = 60

BEGIN_MARKER = 'XML_BEGIN_MARK'
END_MARKER = 'XML_END_MARK'
DONE_MARK = 'REMOTE_JPEG_DONE'


def _ssh_opts():
    return [
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=10',
    ]


def _wrap_ssh(cmd_list):
    if BOARD_SSH_PASS:
        return ['sshpass', '-p', BOARD_SSH_PASS] + cmd_list
    return cmd_list + ['-o', 'BatchMode=yes']


def _remote_pytest_cmd():
    inner = (
        f'cd {REMOTE_TEST_DIR} && '
        f'export PYTHONPATH=/data:/data/athena2_daily_test:$PYTHONPATH && '
        f'python3 -m pytest . -v -s --tb=short --junitxml={REMOTE_XML}'
    )
    escaped = inner.replace("'", "'\"'\"'")
    return f"bash -lc '{escaped}'"


def run_remote_pytest_ssh(ip):
    remote_cmd = _remote_pytest_cmd()
    cmd = _wrap_ssh(['ssh'] + _ssh_opts() + [f'{BOARD_USER}@{ip}', remote_cmd])
    print(f'\n$ ssh {BOARD_USER}@{ip} {remote_cmd}', flush=True)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        return False, str(e)

    lines = []
    deadline = time.time() + PYTEST_TIMEOUT
    try:
        assert proc.stdout is not None
        while True:
            if time.time() > deadline:
                proc.kill()
                lines.append('\nssh pytest timeout\n')
                break
            line = proc.stdout.readline()
            if line == '' and proc.poll() is not None:
                break
            if line:
                print(line, end='', flush=True)
                lines.append(line)
            else:
                time.sleep(0.05)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        raise

    out = ''.join(lines)
    if any(x in out for x in (
        'Permission denied',
        'Connection refused',
        'No route to host',
        'Connection timed out',
        'Could not resolve hostname',
    )):
        return False, out
    if 'sshpass' in out and 'not found' in out:
        return False, out
    return True, out


def run_remote_pytest_serial(board):
    run_cmd(board, 'stty -echo', PROMPT, timeout=5, quiet=0.2)
    try:
        ok, out = run_cmd(
            board,
            f'{_remote_pytest_cmd()} ; echo {DONE_MARK}',
            DONE_MARK,
            timeout=PYTEST_TIMEOUT,
            quiet=2,
            own_line=True,
        )
    finally:
        run_cmd(board, 'stty echo', PROMPT, timeout=5, quiet=0.2)
    return ok, out


def fetch_xml_via_scp(ip):
    local_path = os.path.abspath(LOCAL_XML)
    cmd = _wrap_ssh(['scp'] + _ssh_opts() + [
        f'{BOARD_USER}@{ip}:{REMOTE_XML}',
        local_path,
    ])
    print(f'\n$ scp {BOARD_USER}@{ip}:{REMOTE_XML} {local_path}', flush=True)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=SCP_TIMEOUT)
    except FileNotFoundError as e:
        return None, str(e)
    except subprocess.TimeoutExpired:
        return None, 'scp timeout'
    if r.returncode != 0:
        return None, (r.stderr or r.stdout or 'scp failed')
    with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read().strip(), ''


def _extract_between_markers(text):
    begins = [m.end() for m in re.finditer(re.escape(BEGIN_MARKER), text)]
    if not begins:
        return None
    for start in reversed(begins):
        end = text.find(END_MARKER, start)
        if end == -1:
            continue
        content = text[start:end].strip()
        if content.startswith('<?xml') or content.startswith('<'):
            return content
    return None


def fetch_xml_via_serial(board):
    run_cmd(board, 'stty -echo', PROMPT, timeout=5, quiet=0.2)
    try:
        ok, out = run_cmd(
            board,
            f'printf "%s\\n" {BEGIN_MARKER}; cat {REMOTE_XML}; printf "\\n%s\\n" {END_MARKER}',
            END_MARKER,
            timeout=60,
            quiet=1,
            own_line=True,
        )
    finally:
        run_cmd(board, 'stty echo', PROMPT, timeout=5, quiet=0.2)
    if not ok:
        return None
    return _extract_between_markers(out)


def count_results(xml_text):
    root = ET.fromstring(xml_text)
    total = failures = errors = skipped = 0
    for tc in root.iter('testcase'):
        total += 1
        if tc.find('failure') is not None:
            failures += 1
        elif tc.find('error') is not None:
            errors += 1
        elif tc.find('skipped') is not None:
            skipped += 1
    passed = total - failures - errors - skipped
    return total, passed, failures, errors, skipped


def test_run_remote_jpeg(board, board_ip):
    print(f'\n使用板子 IP: {board_ip}', flush=True)
    print(f'远端测试目录: {REMOTE_TEST_DIR}', flush=True)

    print('\n[网络] 通过 SSH 执行远端 pytest（实时输出）...', flush=True)
    started, out = run_remote_pytest_ssh(board_ip)
    if not started:
        print(f'\n[网络] SSH 不可用，回退串口执行:\n{out[:500]}', flush=True)
        ok, out = run_remote_pytest_serial(board)
        assert ok, f'串口执行远端 pytest 失败/超时\n{out}'

    assert 'No module named pytest' not in out, (
        f'远端缺少 pytest，请确认 test_prepare_athena2_env 已通过\n{out}'
    )
    assert 'No module named \'utils\'' not in out and 'No module named "utils"' not in out, (
        '远端缺少 utils 模块。请把仓库 pytest/utils 拷到板子 /data/utils '
        f'(与 athena2_daily_test 同级)\n{out}'
    )
    assert 'ImportError while loading conftest' not in out, (
        f'远端 conftest 加载失败，pytest 未真正跑起来，因此没有生成 {REMOTE_XML}\n{out}'
    )

    xml_text, err = fetch_xml_via_scp(board_ip)
    if not xml_text:
        print(f'\nscp 拉取失败，回退串口传输: {err}', flush=True)
        xml_text = fetch_xml_via_serial(board)

    assert xml_text, (
        f'无法获取远端测试报告 {REMOTE_XML}。'
        f'通常是远端 pytest 未成功执行，或 scp/串口回传失败。scp错误: {err}'
    )
    assert xml_text.lstrip().startswith('<'), f'报告内容不是合法 XML:\n{xml_text[:200]}'

    local_path = os.path.abspath(LOCAL_XML)
    with open(local_path, 'w', encoding='utf-8') as f:
        f.write(xml_text)
    print(f'\n远端报告已保存: {local_path}', flush=True)

    total, passed, failures, errors, skipped = count_results(xml_text)
    summary = (
        f'远端 JPEG 测试: {passed} passed, {failures} failed, '
        f'{errors} error, {skipped} skipped (共 {total})'
    )
    print(summary, flush=True)

    assert failures == 0 and errors == 0, summary
