import os
import re
import time
import subprocess
import xml.etree.ElementTree as ET
import pytest
from conftest import (
    run_cmd,
    PROMPT,
    REMOTE_TEST_ROOT,
    JPEG_WORKSPACE,
    JPEG_RSYNC_SRC,
    JPEG_RSYNC_USER_PASS,
)

REMOTE_TEST_DIR = REMOTE_TEST_ROOT
REMOTE_XML = '/tmp/jpeg_results.xml'
LOCAL_XML = os.path.join(os.path.dirname(__file__), '..', 'remote_jpeg_results.xml')
BOARD_USER = os.environ.get('BOARD_USER', 'linaro')
BOARD_SSH_PASS = os.environ.get('BOARD_SSH_PASS', 'linaro')
BOARD_PASS = os.environ.get('BOARD_PASS', 'linaro')

PYTEST_TIMEOUT = 1800
RSYNC_TIMEOUT = 1800
SCP_TIMEOUT = 60

BEGIN_MARKER = 'XML_BEGIN_MARK'
END_MARKER = 'XML_END_MARK'
DONE_MARK = 'REMOTE_JPEG_DONE'


def _ssh_opts():
    return [
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=120',
    ]


def _wrap_ssh(cmd_list):
    if BOARD_SSH_PASS:
        return ['sshpass', '-p', BOARD_SSH_PASS] + cmd_list
    return cmd_list + ['-o', 'BatchMode=yes']


def ssh_run_stream(ip, remote_cmd, timeout=600):
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
    deadline = time.time() + timeout
    try:
        assert proc.stdout is not None
        while True:
            if time.time() > deadline:
                proc.kill()
                lines.append('\ntimeout\n')
                break
            line = proc.stdout.readline()
            if line == '' and proc.poll() is not None:
                break
            if line:
                print(line, end='', flush=True)
                lines.append(line)
            else:
                time.sleep(0.05)
        rc = proc.wait(timeout=5)
    except Exception:
        proc.kill()
        raise
    return rc == 0, ''.join(lines)


def sync_jpeg_workspace(ip):
    ok, out = ssh_run_stream(
        ip,
        f"echo {BOARD_PASS} | sudo -S -p '' bash -c "
        f"'command -v rsync >/dev/null && command -v sshpass >/dev/null || "
        f"(apt-get update -qq && apt-get install -y -qq rsync sshpass)'",
        timeout=300,
    )
    assert ok, f'install rsync/sshpass failed\n{out}'

    ok, out = ssh_run_stream(
        ip,
        f'mkdir -p {JPEG_WORKSPACE} && '
        f'sshpass -p {JPEG_RSYNC_USER_PASS} rsync -arvcL '
        f'-e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" '
        f'{JPEG_RSYNC_SRC} {JPEG_WORKSPACE}/ && '
        f'test -d {JPEG_WORKSPACE}/opencvjpu && test -d {JPEG_WORKSPACE}/bmapi && '
        f'ls {JPEG_WORKSPACE}/opencvjpu | head',
        timeout=RSYNC_TIMEOUT,
    )
    assert ok, f'jpeg rsync failed\n{out}'
    assert 'Permission denied' not in out
    assert 'command not found' not in out
    return out


def _remote_pytest_cmd():
    inner = (
        f'cd {REMOTE_TEST_DIR} && '
        f'export TEST_WORKSPACE={JPEG_WORKSPACE} && '
        f'export PYTHONPATH=/data:/data/athena2_daily_test:$PYTHONPATH && '
        f'python3 -m pytest -m jpeg -v -s --tb=short --junitxml={REMOTE_XML}'
    )
    escaped = inner.replace("'", "'\"'\"'")
    return f"bash -lc '{escaped}'"


def run_remote_pytest_ssh(ip):
    return ssh_run_stream(ip, _remote_pytest_cmd(), timeout=PYTEST_TIMEOUT)


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
    print(f'BOARD_IP={board_ip}', flush=True)
    print(f'TEST_WORKSPACE={JPEG_WORKSPACE}', flush=True)

    sync_jpeg_workspace(board_ip)

    started, out = run_remote_pytest_ssh(board_ip)
    if not started:
        ok, out = run_remote_pytest_serial(board)
        assert ok, f'remote pytest via serial failed\n{out}'

    assert 'No module named pytest' not in out, f'missing pytest\n{out}'
    assert "No module named 'utils'" not in out and 'No module named "utils"' not in out, (
        f'missing utils\n{out}'
    )
    assert 'ImportError while loading conftest' not in out, f'conftest import error\n{out}'

    xml_text, err = fetch_xml_via_scp(board_ip)
    if not xml_text:
        xml_text = fetch_xml_via_serial(board)

    assert xml_text, f'failed to fetch {REMOTE_XML}: {err}'
    assert xml_text.lstrip().startswith('<'), f'invalid xml:\n{xml_text[:200]}'

    local_path = os.path.abspath(LOCAL_XML)
    with open(local_path, 'w', encoding='utf-8') as f:
        f.write(xml_text)

    total, passed, failures, errors, skipped = count_results(xml_text)
    summary = (
        f'jpeg: {passed} passed, {failures} failed, '
        f'{errors} error, {skipped} skipped (total {total})'
    )
    print(summary, flush=True)
    assert failures == 0 and errors == 0, summary
