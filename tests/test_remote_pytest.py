import os
import re
import subprocess
import xml.etree.ElementTree as ET
import pytest
from conftest import run_cmd, PROMPT, REMOTE_JPEG_DIR

REMOTE_TEST_DIR = REMOTE_JPEG_DIR
REMOTE_XML = '/tmp/jpeg_results.xml'
LOCAL_XML = os.path.join(os.path.dirname(__file__), '..', 'remote_jpeg_results.xml')
BOARD_USER = os.environ.get('BOARD_USER', 'linaro')

PYTEST_TIMEOUT = 1800
SCP_TIMEOUT = 60

BEGIN_MARKER = 'XML_BEGIN_MARK'
END_MARKER = 'XML_END_MARK'
DONE_MARK = 'REMOTE_JPEG_DONE'


def _ssh_base(ip):
    return [
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=10',
        '-o', 'BatchMode=yes',
    ]


def run_remote_pytest(board):
    run_cmd(board, 'stty -echo', PROMPT, timeout=5, quiet=0.2)
    try:
        ok, out = run_cmd(
            board,
            f'cd {REMOTE_TEST_DIR} && '
            f'python3 -m pytest . -v --tb=short --junitxml={REMOTE_XML} ; '
            f'echo {DONE_MARK}',
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
    cmd = ['scp'] + _ssh_base(ip) + [
        f'{BOARD_USER}@{ip}:{REMOTE_XML}',
        local_path,
    ]
    print(f'\n$ {" ".join(cmd)}', flush=True)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=SCP_TIMEOUT)
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

    ok, out = run_remote_pytest(board)
    assert ok, f'远端 pytest 执行超时（{PYTEST_TIMEOUT}s）'
    assert 'No module named pytest' not in out, f'远端缺少 pytest，请确认 test_prepare_athena2_env 已通过\n{out}'

    xml_text, err = fetch_xml_via_scp(board_ip)
    if not xml_text:
        print(f'\nscp 拉取失败，回退串口传输: {err}', flush=True)
        xml_text = fetch_xml_via_serial(board)

    assert xml_text, f'无法获取远端测试报告 {REMOTE_XML}'
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
