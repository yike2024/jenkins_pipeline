"""
通过串口在板子上执行 /data/jpeg 目录下的 pytest 测试，
将远端 JUnit XML 报告拉回本地保存为 remote_jpeg_results.xml，
供 Jenkins junit 插件一并展示每条远端用例的红绿状态。

本文件自身只包含一个"调度"用例 test_run_remote_jpeg，
负责触发远端执行 + 回传报告。若远端有失败用例，此用例也会标记失败。
"""
import os
import re
import xml.etree.ElementTree as ET
import pytest
from conftest import run_cmd

REMOTE_TEST_DIR = '/data/jpeg'
REMOTE_XML = '/tmp/jpeg_results.xml'
LOCAL_XML = os.path.join(os.path.dirname(__file__), '..', 'remote_jpeg_results.xml')

PYTEST_TIMEOUT = 1800
CAT_TIMEOUT = 60

BEGIN_MARKER = '===XMLBEGIN==='
END_MARKER = '===XMLEND==='


def run_remote_pytest(board):
    ok, out = run_cmd(
        board,
        f'cd {REMOTE_TEST_DIR} && '
        f'python3 -m pytest . -v --tb=short --junitxml={REMOTE_XML} ; '
        f'echo REMOTE_PYTEST_DONE',
        'REMOTE_PYTEST_DONE',
        timeout=PYTEST_TIMEOUT,
        quiet=2,
    )
    return ok, out


def fetch_xml_via_serial(board):
    ok, out = run_cmd(
        board,
        f'echo {BEGIN_MARKER} && cat {REMOTE_XML} && echo {END_MARKER}',
        END_MARKER,
        timeout=CAT_TIMEOUT,
        quiet=1,
    )
    if not ok:
        return None
    m = re.search(
        re.escape(BEGIN_MARKER) + r'\s*(.*?)\s*' + re.escape(END_MARKER),
        out,
        re.DOTALL,
    )
    if not m:
        return None
    return m.group(1).strip()


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


def test_run_remote_jpeg(board):
    ok, out = run_remote_pytest(board)
    assert ok, f'远端 pytest 执行超时（{PYTEST_TIMEOUT}s）'

    xml_text = fetch_xml_via_serial(board)
    assert xml_text, f'无法通过串口获取远端报告 {REMOTE_XML}'

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
