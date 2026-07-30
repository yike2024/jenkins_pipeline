import os
import re
import time
import subprocess
import pytest
import serial
from serial import SerialException

PORT = '/dev/ttyUSB0'
BAUD = 115200
PROMPT = 'linaro@sophon'
PROMPT_RE = re.compile(r'l?inaro@sophon')
LOGIN_RE = re.compile(r'login:\s*$', re.IGNORECASE | re.MULTILINE)
PASSWORD_RE = re.compile(r'password:\s*$', re.IGNORECASE | re.MULTILINE)
BOARD_USER = os.environ.get('BOARD_USER', 'linaro')
BOARD_PASS = os.environ.get('BOARD_PASS', 'linaro')
BOARD_IP_FILE = os.path.join(os.path.dirname(__file__), '..', 'board_ip.txt')
REMOTE_TEST_ROOT = '/data/athena2_daily_test'
REMOTE_JPEG_DIR = f'{REMOTE_TEST_ROOT}/multimedia/jpeg'

ANSI_RE = re.compile(
    r'\x1b\[[0-?]*[ -/]*[@-~]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1b[@-Z\\-_]'
)
IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def clean(text):
    text = ANSI_RE.sub('', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*$', '', text)
    text = text.replace('\r', '')
    return text


def has_prompt(text):
    return bool(PROMPT_RE.search(text))


def has_login_prompt(text):
    return bool(LOGIN_RE.search(text.rstrip()))


def has_password_prompt(text):
    return bool(PASSWORD_RE.search(text.rstrip()))


def try_serial_login(ser, text, state):
    now = time.time()
    if has_password_prompt(text):
        if now - state.get('last_password', 0) > 2:
            print(f'\n[串口] 检测到 Password，输入密码', flush=True)
            ser.write((BOARD_PASS + '\n').encode())
            state['last_password'] = now
            state['login_sent'] = False
        return True
    if has_login_prompt(text):
        if now - state.get('last_login', 0) > 2:
            print(f'\n[串口] 检测到 login，输入用户名 {BOARD_USER}', flush=True)
            ser.write((BOARD_USER + '\n').encode())
            state['last_login'] = now
            state['login_sent'] = True
        return True
    return False


def parse_board_ip(text):
    ips = []
    for ip in IP_RE.findall(text):
        if ip.startswith('127.') or ip.startswith('169.254.'):
            continue
        if ip not in ips:
            ips.append(ip)
    return ips[0] if ips else None


def port_users(port=PORT):
    try:
        out = subprocess.check_output(
            ['fuser', '-v', port],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
        return out.strip() or '(none)'
    except Exception:
        return '(无法查询，请确认未运行 minicom/screen，且无其他 Jenkins 任务占用)'


def open_serial(port=PORT, baud=BAUD, retries=3):
    if not os.path.exists(port):
        raise SerialException(f'串口不存在: {port}，当前设备: {sorted(os.listdir("/dev"))}')
    last_err = None
    for i in range(retries):
        try:
            kwargs = dict(port=port, baudrate=baud, timeout=1)
            try:
                kwargs['exclusive'] = True
                ser = serial.Serial(**kwargs)
            except (TypeError, ValueError):
                kwargs.pop('exclusive', None)
                ser = serial.Serial(**kwargs)
            time.sleep(0.3)
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass
            return ser
        except SerialException as e:
            last_err = e
            time.sleep(0.5 * (i + 1))
    raise SerialException(
        f'无法打开 {port}: {last_err}\n占用情况:\n{port_users(port)}'
    )


def _serial_read(ser, size):
    try:
        if size <= 0:
            return b''
        return ser.read(size) or b''
    except SerialException:
        time.sleep(0.05)
        return b''


def _serial_in_waiting(ser):
    try:
        return ser.in_waiting
    except SerialException:
        return 0


def fetch_board_ip(ser):
    ok, out = run_cmd(ser, 'hostname -I', PROMPT, timeout=10)
    if not ok:
        return None, out
    return parse_board_ip(out), out


def _stream_delta(text, printed):
    if len(text) > printed:
        print(text[printed:], end='', flush=True)
        return len(text)
    return printed


def _expect_matched(text, expect, own_line):
    if not expect:
        return False
    if expect == PROMPT or expect == 'linaro@sophon':
        return has_prompt(text)
    if own_line:
        return bool(re.search(r'(?m)^' + re.escape(expect) + r'\s*$', text))
    return expect in text


def run_cmd(ser, cmd, expect, timeout=10, quiet=0.5, stream=True, own_line=False):
    if stream:
        print(f'\n$ {cmd}', flush=True)
    try:
        ser.reset_input_buffer()
    except SerialException:
        pass
    ser.write((cmd + '\n').encode())
    buf = b''
    printed = 0
    deadline = time.time() + timeout

    while time.time() < deadline:
        n = _serial_in_waiting(ser)
        buf += _serial_read(ser, n or 1)
        text = clean(buf.decode(errors='replace'))
        if stream:
            printed = _stream_delta(text, printed)
        if _expect_matched(text, expect, own_line):
            end = time.time() + quiet
            while time.time() < end:
                n = _serial_in_waiting(ser)
                if n:
                    buf += _serial_read(ser, n)
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


def wait_for_shell(ser, timeout=60):
    print('\n[串口] 尝试唤醒 shell...', flush=True)
    try:
        ser.reset_input_buffer()
    except SerialException:
        pass

    ser.write(b'\x03')
    time.sleep(0.3)
    ser.write(b'\n')
    time.sleep(0.3)

    buf = b''
    printed = 0
    deadline = time.time() + timeout
    last_nudge = 0
    login_state = {}
    while time.time() < deadline:
        n = _serial_in_waiting(ser)
        chunk = _serial_read(ser, n or 1)
        if chunk:
            buf += chunk
        text = clean(buf.decode(errors='replace'))
        printed = _stream_delta(text, printed)
        if has_prompt(text):
            print(flush=True)
            run_cmd(ser, 'stty echo', PROMPT, timeout=5, quiet=0.2)
            return True, text

        if try_serial_login(ser, text, login_state):
            time.sleep(0.5)
            continue

        now = time.time()
        if now - last_nudge > 3:
            ser.write(b'\n')
            last_nudge = now
        time.sleep(0.05)

    text = clean(buf.decode(errors='replace'))
    print(flush=True)
    return False, text


@pytest.fixture(scope='session')
def board():
    try:
        ser = open_serial()
    except SerialException as e:
        pytest.fail(str(e))
    ok, out = wait_for_shell(ser, timeout=30)
    if not ok:
        ser.close()
        pytest.fail(
            f'连不上板子 shell（提示符 {PROMPT}），检查板子是否已开机\n'
            f'占用情况:\n{port_users()}\n输出:\n{out}'
        )
    yield ser
    try:
        ser.write(b'\x03\nstty echo\n')
        time.sleep(0.2)
        ser.close()
    except Exception:
        pass


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


def pytest_collection_modifyitems(items):
    def _order(item):
        nodeid = item.nodeid
        if 'test_serial.py' in nodeid:
            return (0, nodeid)
        if 'test_remote_pytest.py' in nodeid:
            return (2, nodeid)
        return (1, nodeid)

    items.sort(key=_order)
