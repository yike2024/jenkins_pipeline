import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from conftest import (
    open_serial,
    clean,
    has_prompt,
    has_login_prompt,
    fetch_board_ip,
    try_serial_login,
    _serial_in_waiting,
    _serial_read,
    _stream_delta,
    BOARD_IP_FILE,
    BOARD_PASS,
    PROMPT,
    run_cmd,
)


def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
    ignore_prompt_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 45

    print(f'[串口] 开始监控 OTA/U-Boot 日志，最长 {timeout}s', flush=True)
    print(f'[串口] 前 {ignore_prompt_sec}s 忽略旧 shell（等待重启）', flush=True)

    ser = open_serial()
    buf = b''
    printed = 0
    start = time.time()
    deadline = start + timeout
    last_nudge = 0
    prompt_ready_after = start + ignore_prompt_sec
    login_state = {}
    saw_boot = False

    try:
        while time.time() < deadline:
            n = _serial_in_waiting(ser)
            chunk = _serial_read(ser, n or 1)
            if chunk:
                buf += chunk
            text = clean(buf.decode(errors='replace'))
            printed = _stream_delta(text, printed)

            now = time.time()
            low = text.lower()
            if any(x in low for x in ('u-boot', 'starting kernel', 'mmc write', 'sophon login:')):
                saw_boot = True

            if now >= prompt_ready_after or saw_boot:
                if try_serial_login(ser, text, login_state):
                    time.sleep(0.3)
                    continue

            if (now >= prompt_ready_after or saw_boot) and has_prompt(text):
                login_state['logged_in'] = True
                print('\n[串口] 已登录系统，执行 sudo bm_version ...', flush=True)
                ok, ver_out = run_cmd(
                    ser,
                    f'echo {BOARD_PASS} | sudo -S -p "" bm_version',
                    'SophonSDK',
                    timeout=30,
                    quiet=1,
                )
                if not ok:
                    ok, ver_out = run_cmd(ser, 'bm_version', 'SophonSDK', timeout=20, quiet=1)
                if not ok:
                    print('[串口] bm_version 未拿到预期输出，继续等待...', flush=True)
                    buf = b''
                    printed = 0
                    time.sleep(2)
                    continue

                ip, ip_out = fetch_board_ip(ser)
                if not ip:
                    print('[串口] 尚未拿到 IP，继续等待...', flush=True)
                    buf = b''
                    printed = 0
                    time.sleep(2)
                    continue

                with open(os.path.abspath(BOARD_IP_FILE), 'w', encoding='utf-8') as f:
                    f.write(ip + '\n')
                print('\n[串口] OTA 后板子已恢复', flush=True)
                print(f'BOARD_IP={ip}', flush=True)
                print('--- bm_version ---', flush=True)
                print(ver_out, flush=True)
                return 0

            if now - last_nudge > 5 and (now >= prompt_ready_after or saw_boot):
                if has_prompt(text) or has_login_prompt(text) or 'password:' in _tail_lower(text):
                    pass
                else:
                    ser.write(b'\n')
                last_nudge = now
            time.sleep(0.05)

        print('\n[串口] 等待超时：未在限定时间内完成登录/bm_version', flush=True)
        return 1
    finally:
        try:
            ser.close()
        except Exception:
            pass


def _tail_lower(text, n=240):
    t = text[-n:] if len(text) > n else text
    return t.lower()


if __name__ == '__main__':
    sys.exit(main())
