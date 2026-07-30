import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from conftest import (
    open_serial,
    clean,
    has_prompt,
    fetch_board_ip,
    _serial_in_waiting,
    _serial_read,
    _stream_delta,
    BOARD_IP_FILE,
    PROMPT,
    run_cmd,
)


def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
    ignore_prompt_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 45

    print(f'[串口] 开始监控 OTA/U-Boot 日志，最长 {timeout}s', flush=True)
    print(f'[串口] 前 {ignore_prompt_sec}s 忽略旧 shell 提示符（等待重启进入 uboot）', flush=True)

    ser = open_serial()
    buf = b''
    printed = 0
    start = time.time()
    deadline = start + timeout
    last_nudge = 0
    prompt_ready_after = start + ignore_prompt_sec

    try:
        while time.time() < deadline:
            n = _serial_in_waiting(ser)
            chunk = _serial_read(ser, n or 1)
            if chunk:
                buf += chunk
            text = clean(buf.decode(errors='replace'))
            printed = _stream_delta(text, printed)

            now = time.time()
            if now >= prompt_ready_after and has_prompt(text):
                print('\n[串口] 检测到系统 shell 提示符，确认网络...', flush=True)
                time.sleep(2)
                ok, out = run_cmd(ser, '', PROMPT, timeout=10, quiet=0.5)
                if not ok:
                    continue
                ip, ip_out = fetch_board_ip(ser)
                if not ip:
                    print('[串口] 尚未拿到 IP，继续等待...', flush=True)
                    buf = b''
                    printed = 0
                    continue

                with open(os.path.abspath(BOARD_IP_FILE), 'w', encoding='utf-8') as f:
                    f.write(ip + '\n')
                print(f'\n[串口] OTA 后板子已恢复', flush=True)
                print(f'BOARD_IP={ip}', flush=True)
                return 0

            if now - last_nudge > 5 and now >= prompt_ready_after:
                ser.write(b'\n')
                last_nudge = now
            time.sleep(0.05)

        print('\n[串口] 等待超时：未在限定时间内回到 shell', flush=True)
        return 1
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
