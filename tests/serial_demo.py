#!/usr/bin/env python3
"""serial_test.py - 串口自动化测试框架"""
import serial
import time
import sys
import re

PORT = '/dev/ttyUSB0'
BAUD = 115200
PROMPT = 'linaro@sophon'

ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')

# ==================== 测试用例表：加 case 就加这里 ====================
# (用例名, 命令, 期望输出包含的字符串, 超时秒)
TESTS = [
    ('系统信息',   'cat /etc/os-release', 'PRETTY_NAME',        5),
    ('BM版本',     'bm_version',          'SophonSDK',          5),
    # 示例：继续往下加
    # ('内存信息', 'free -h',             'Mem:',               5),
    # ('磁盘挂载', 'df -h /',             '/dev/',              5),
    # ('网络连通', 'ping -c 3 8.8.8.8',   '3 received',        10),
]
# ====================================================================

def clean(text):
    return ANSI_RE.sub('', text)

def run_cmd(ser, cmd, expect, timeout=10, quiet=0.5):
    ser.reset_input_buffer()
    ser.write((cmd + '\n').encode())
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        buf += ser.read(ser.in_waiting or 1)
        text = clean(buf.decode(errors='replace'))
        if expect in text:
            end = time.time() + quiet
            while time.time() < end:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    end = time.time() + quiet
                else:
                    time.sleep(0.05)
            return True, clean(buf.decode(errors='replace'))
    return False, clean(buf.decode(errors='replace'))

def main():
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f'已打开 {PORT} @ {BAUD}\n')

    # 唤醒 shell
    ok, out = run_cmd(ser, '', PROMPT, timeout=5)
    if not ok:
        print('FAIL: 连不上板子 shell，检查板子是否已开机进系统')
        sys.exit(1)

    results = []
    for name, cmd, expect, timeout in TESTS:
        print(f'----- [{name}] $ {cmd}')
        ok, out = run_cmd(ser, cmd, expect, timeout=timeout)
        print(out)
        results.append((name, ok))
        print(f'----- [{name}] {"PASS" if ok else "FAIL"}\n')

    # 汇总报告
    passed = sum(1 for _, ok in results if ok)
    print('=' * 40)
    print(f'测试汇总: {passed}/{len(results)} 通过')
    for name, ok in results:
        print(f'  {"✅" if ok else "❌"} {name}')
    print('=' * 40)

    ser.close()
    sys.exit(0 if passed == len(results) else 1)   # 有失败 → Jenkins 标红

if __name__ == '__main__':
    main()

