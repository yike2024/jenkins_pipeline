# 串口自动化测试（tests/）

基于 **pytest + pyserial** 的硬件串口自动化测试。通过 `/dev/ttyUSB0` 连接
开发板（linaro@sophon, Ubuntu 22.04），在板子的 shell 里执行命令并断言输出，
生成 JUnit XML 报告供 Jenkins 展示。

## 目录结构

```
tests/
├── conftest.py        # 框架层：串口连接 fixture、run_cmd 工具函数（一般不用改）
├── test_serial.py     # 用例层：TESTS 用例表（加测试改这里）
└── README.md          # 本文档
```

## 工作原理

```
Jenkins 任务 → python3 -m pytest tests/ --junitxml=results.xml
    ↓
pytest 自动发现 test_*.py 中的 test_* 函数（无需注册）
    ↓
conftest.py 的 board fixture：打开串口 → 验证 shell 提示符 → 所有用例共享该连接
    ↓
TESTS 表中每行生成一个独立用例：发命令 → 等期望字符串 → 断言
    ↓
results.xml → Jenkins junit 插件 → 网页红绿报告 + 趋势图
```

核心函数 `run_cmd(ser, cmd, expect, timeout, quiet)`：
发送命令，等待输出中出现 `expect` 字符串（最长等 `timeout` 秒），匹配后
再静默 `quiet` 秒收齐剩余输出。自动过滤 ANSI 终端控制码。

## 本地调试（服务器上手动跑）

```bash
# 进入 Jenkins 容器（pyserial/pytest 已装好，串口已透传）
docker exec -it jenkins bash
cd /var/jenkins_home/workspace/edge_auto_test

# 跑全部用例（显示 print 输出）
python3 -m pytest tests/ -v -s

# 只跑一条用例
python3 -m pytest tests/ -v -s -k "系统信息"
```

> 注意：串口是独占的，手动调试前先退出 minicom，并确认 Jenkins 没有在跑测试任务。

## 添加测试用例

### 方式一：往 TESTS 表加一行（90% 的场景）

编辑 `test_serial.py` 顶部的 `TESTS`：

```python
TESTS = [
    ('系统信息', 'cat /etc/os-release', 'PRETTY_NAME', 5),
    ('BM版本',   'bm_version',          'SophonSDK',   5),
    ('内存信息', 'free -h',             'Mem:',        5),     # ← 新增一行就是一个用例
]
```

每行四要素：`(用例名, 命令, 期望字符串, 超时秒)`

**期望字符串的选择原则**：
- 挑输出中"每次必有、内容稳定"的字符串（标签、关键字）
- 不要匹配版本号、IP、时间戳等会变的值，否则升级后要改脚本
- 拿不准时先在 minicom 里手动执行命令，观察实际输出

**超时的选择原则**：
- 普通命令 5 秒足够
- 本身耗时的命令（ping、dd、压力测试）按实际耗时 + 余量给

### 方式二：写独立 test 函数（复杂场景）

需要多步交互、条件判断、reboot 重连等逻辑时，在 `test_serial.py` 中直接写函数：

```python
def test_reboot(board):
    """重启后重新等到系统启动"""
    ok, _ = run_cmd(board, 'sudo reboot', 'reboot', timeout=5)
    assert ok
    # 等待板子重新进系统（启动日志 + 提示符，时间给足）
    ok, out = run_cmd(board, '', 'linaro@sophon', timeout=120)
    assert ok, '重启后 120 秒内未回到 shell'
```

规则：
- 函数名以 `test_` 开头即被自动执行，无需注册
- 参数写 `board` 即自动获得串口连接（fixture 注入）
- 用 `assert` 判定成败，失败信息会进 Jenkins 报告

### 方式三：自定义 fixture（跨用例的准备工作）

在 `conftest.py` 中添加，例如所有用例前先挂载 NFS：

```python
@pytest.fixture(scope='session')
def nfs(board):
    ok, out = run_cmd(board, 'mount -t nfs 10.0.0.1:/share /mnt', '', timeout=10)
    assert ok, 'NFS 挂载失败'
    return '/mnt'
```

用例中声明参数即可使用：`def test_xxx(board, nfs):`

## Jenkins 集成

测试任务 Pipeline 关键配置（Jenkinsfile 在仓库根目录的 `edge_auto_test`）：

```groovy
sh 'python3 -m pytest tests/ -v --junitxml=results.xml --tb=short'
...
post { always { junit 'results.xml' } }
```

- 用例全过 → 构建 SUCCESS（蓝）
- 有用例失败 → 构建 UNSTABLE（黄），网页 Test Result 中定位失败用例及串口输出
- 任务已配置 `disableConcurrentBuilds()`，串口独占，不会并发冲突

## 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `Permission denied: /dev/ttyUSB0` | 容器内设备权限被重置 | 容器内 `sudo chmod 666 /dev/ttyUSB0`（容器重建后由 dialout 组接管，不会再出现） |
| 用例超时 FAIL，但 minicom 里命令正常 | expect 字符串不匹配（大小写/多余空格/提示符变了） | 看报告中捕获的实际输出，修正 expect |
| 输出有 `[?2004h` 等乱码 | 未走 clean() 过滤 | 确认用的是 conftest.py 里的 run_cmd，不要自己 read |
| 连不上板子 shell | 板子未开机 / 串口被 minicom 占用 / 设备名变了（ttyUSB1） | 检查板子状态；退出 minicom；`ls /dev/ttyUSB*` 确认设备名 |
| 输出被截断只看到前几行 | quiet 太短，输出没收完 | 该用例调用时加大 quiet，如 `run_cmd(..., quiet=1.0)` |

## 环境依赖（已固化，无需手动安装）

- Jenkins 容器镜像：pyserial、pytest（见 Dockerfile）
- 串口透传：容器 privileged 模式 + group_add dialout（见 docker-compose.yml）
- 板子：已通过串口线连接服务器 USB，波特率 115200（改波特率改 conftest.py 的 BAUD）

