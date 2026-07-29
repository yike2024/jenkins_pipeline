import os
import re
import time
import pytest
import serial

PORT = '/dev/ttyUSB0'
BAUD = 115200
PROMPT = 'linaro@sophon'
BOARD_IP_FILE = os.path.join(os.path.dirname(__file__), '..', 'board_ip.txt')

ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def clean(text):
    return ANSI_RE.sub('', text)


def parse_board_ip(text):
    ips = []
    for ip in IP_RE.findall(text):
        if ip.startswith('127.') or ip.startswith('169.254.'):
            continue
        if ip not in ips:
            ips.append(ip)
    return ips[0] if ips else None


def fetch_board_ip(ser):
    ok, out = run_cmd(ser, 'hostname -I', PROMPT, timeout=5)
    if not ok:
        return None, out
    return parse_board_ip(out), out


def _stream_delta(text, printed):
    if len(text) > printed:
        print(text[printed:], end='', flush=True)
        return len(text)
    return printed


def run_cmd(ser, cmd, expect, timeout=10, quiet=0.5, stream=True):
    if stream:
        print(f'\n$ {cmd}', flush=True)
    ser.reset_input_buffer()
    ser.write((cmd + '\n').encode())
    buf = b''
    printed = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        buf += ser.read(ser.in_waiting or 1)
        text = clean(buf.decode(errors='replace'))
        if stream:
            printed = _stream_delta(text, printed)
        if expect in text:
            end = time.time() + quiet
            while time.time() < end:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    text = clean(buf.decode(errors='replace'))
                    if stream:
                        printed = _stream_delta(text, printed)
                    end = time.time() + quiet
                else:
                    time.sleep(0.05)
            text = clean(buf.decode(errors='replace'))
            if stream:
                _stream_delta(text, printed)
                print(flush=True)
            return True, text
    text = clean(buf.decode(errors='replace'))
    if stream:
        _stream_delta(text, printed)
        print(flush=True)
    return False, text


@pytest.fixture(scope='session')
def board():
    ser = serial.Serial(PORT, BAUD, timeout=1)
    ok, out = run_cmd(ser, '', PROMPT, timeout=5)
    if not ok:
        ser.close()
        pytest.fail(f'连不上板子 shell（提示符 {PROMPT}），检查板子是否已开机')
    yield ser
    ser.close()


@pytest.fixture(scope='session')
def board_ip(board):
    ip, out = fetch_board_ip(board)
    if not ip:
        pytest.fail(f'无法获取板子 IP，请检查网口是否已就绪\n{out}')
    os.environ['BOARD_IP'] = ip
    with open(os.path.abspath(BOARD_IP_FILE), 'w', encoding='utf-8') as f:
        f.write(ip + '\n')
    print(f'\n板子 IP: {ip}', flush=True)
    return ip
