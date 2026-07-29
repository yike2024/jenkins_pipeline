import re
import time
import pytest
import serial

PORT = '/dev/ttyUSB0'
BAUD = 115200
PROMPT = 'linaro@sophon'

ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')


def clean(text):
    return ANSI_RE.sub('', text)


def run_cmd(ser, cmd, expect, timeout=10, quiet=0.5):
    """发命令，等 expect 出现后再静默 quiet 秒收齐输出。返回 (成功, 输出)"""
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


@pytest.fixture(scope='session')
def board():
    """整个测试会话共享一个串口连接，所有用例跑完才关闭"""
    ser = serial.Serial(PORT, BAUD, timeout=1)
    ok, out = run_cmd(ser, '', PROMPT, timeout=5)
    if not ok:
        ser.close()
        pytest.fail(f'连不上板子 shell（提示符 {PROMPT}），检查板子是否已开机')
    yield ser
    ser.close()

