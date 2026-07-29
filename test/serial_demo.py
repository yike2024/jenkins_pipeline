#!/usr/bin/env python3
"""serial_demo.py - 串口自动化最小示例"""
import serial
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 115200

def run_cmd(ser, cmd, expect, timeout=10):
    """发一条命令，等到期望字符串出现为止。返回 (是否成功, 输出)"""
    ser.reset_input_buffer()              # 清空接收缓冲区，避免读到上一条命令的残留
    ser.write((cmd + '\n').encode())      # 发命令（相当于 minicom 里打字+回车）
    buf = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        buf += ser.read(ser.in_waiting or 1)   # 读串口输出
        if expect.encode() in buf:             # 等到期望内容 → 成功
            return True, buf.decode(errors='replace')
    return False, buf.decode(errors='replace') # 超时 → 失败

def main():
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f'已打开 {PORT} @ {BAUD}')

    # 唤醒 shell：先发个回车，等命令行提示符（按你板子的实际提示符改，比如 '#' 或 '~ #'）
    ok, out = run_cmd(ser, '', '#', timeout=5)
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

