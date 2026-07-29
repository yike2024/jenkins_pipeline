import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from conftest import open_serial, wait_for_shell, fetch_board_ip


def main():
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        ser = open_serial()
        ok, out = wait_for_shell(ser, timeout=30)
        if not ok:
            ser.close()
            print(f'连不上板子 shell\n{out}', file=sys.stderr)
            sys.exit(1)
        ip, out = fetch_board_ip(ser)
        ser.close()
    finally:
        sys.stdout = real_stdout

    if not ip:
        print(f'无法解析板子 IP\n{out}', file=sys.stderr)
        sys.exit(1)
    print(ip)


if __name__ == '__main__':
    main()
