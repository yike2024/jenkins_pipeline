#!/usr/bin/env python3
"""serial_demo.py - 串口自动化最小示例"""
import serial
import time
import sys
import re

# ANSI 转义序列过滤
PORT = '/dev/ttyUSB0'
BAUD = 115200
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')

def clean(text):
    """去掉终端控制码，日志更干净"""
    return ANSI_RE.sub('', text)

def run_cmd(ser, cmd, expect, timeout=10):
    ser.reset_input_buffer()
    ser.write((cmd + '\n').encode())
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        buf += ser.read(ser.in_waiting or 1)
        text = ANSI_RE.sub('', buf.decode(errors='replace'))
        if expect in text:
            return True, text
    return False, ANSI_RE.sub('', buf.decode(errors='replace'))


def main():
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f'已打开 {PORT} @ {BAUD}')

    # 唤醒 shell：先发个回车，等命令行提示符（按你板子的实际提示符改，比如 '#' 或 '~ #'）
    ok, out = run_cmd(ser, '', 'linaro@sophon', timeout=5)

    print(out)

    # 跑一条测试命令：比如查看系统版本
    ok, out = run_cmd(ser, 'cat /etc/os-release', 'PRETTY_NAME', timeout=5)
    print(out)
    if not ok:
        print('FAIL: 没有读到系统信息')
        sys.exit(1)          # 退出码非 0 → Jenkins 判定构建失败

    print('PASS: 串口通信正常')
    ser.close()

if __name__ == '__main__':
    main()

