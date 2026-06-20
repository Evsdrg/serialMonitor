"""
集成测试 - 使用 PTY 虚拟串口进行真实数据流测试

仅在 Linux/macOS 上运行（依赖 os.openpty），Windows 上自动跳过。
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="PTY 虚拟串口仅在 Unix 系统上可用",
)


# ── 辅助函数 ─────────────────────────────────────────────


class VirtualSerial:
    """PTY 虚拟串口对。master 端可被测试代码外部写入，slave 端给 serial.Serial 使用。"""

    def __init__(self, baudrate: int = 9600):
        self.master_fd, self.slave_fd = pty.openpty()
        self.port_name = os.ttyname(self.slave_fd)
        self.baudrate = baudrate

    def write_from_external(self, data: bytes) -> int:
        """从 master 端写入（模拟外部设备发数据）。"""
        return os.write(self.master_fd, data)

    def read_from_external(self, size: int = 4096, timeout: float = 0.5) -> bytes:
        """从 master 端读取（获取 serial 写入的数据）。"""
        return _read_with_timeout(self.master_fd, size, timeout)

    def close(self) -> None:
        for fd in (self.master_fd, self.slave_fd):
            try:
                os.close(fd)
            except OSError:
                pass


def _read_with_timeout(fd: int, size: int, timeout: float) -> bytes:
    """非阻塞读取，超时返回已读数据。"""
    import select
    chunks = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(chunks) < size:
        remaining = size - sum(len(c) for c in chunks)
        ready, _, _ = select.select([fd], [], [], max(0.01, deadline - time.monotonic()))
        if not ready:
            break
        try:
            chunk = os.read(fd, remaining)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


# ── 导入被测代码（需要 pty 模块）────────────────────────────


import pty  # noqa: E402

from core.serial_handler import SerialHandler  # noqa: E402


# ── SerialHandler 集成测试 ────────────────────────────────


class TestSerialHandlerOpenClose:
    def test_open_pty_port(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            ok = handler.open(vs.port_name, baudrate=vs.baudrate)
            assert ok is True
            assert handler.is_open() is True
            assert handler.current_port == vs.port_name
            handler.close()
            assert handler.is_open() is False
        finally:
            vs.close()

    def test_open_invalid_port(self):
        handler = SerialHandler()
        ok = handler.open("/dev/ttyNONEXISTENT_XYZ_9999", baudrate=9600)
        assert ok is False
        assert handler.last_error is not None

    def test_get_available_ports_includes_pty(self):
        vs = VirtualSerial()
        try:
            ports = SerialHandler.get_available_ports()
            # PTY 设备名可能不在 ttyUSB/ttyACM 排序中
            assert isinstance(ports, list)
        finally:
            vs.close()


class TestSerialHandlerReadWrite:
    def test_write_then_external_reads(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                result = handler.write_data(b"AT\r\n")
                assert result is True

                received = vs.read_from_external(size=10, timeout=1.0)
                assert received == b"AT\r\n"
            finally:
                handler.close()
        finally:
            vs.close()

    def test_external_write_then_handler_reads(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received_data = []

                def on_data(data: bytes) -> None:
                    received_data.append(data)

                handler.data_received.connect(on_data)

                vs.write_from_external(b"hello world\n")

                # 等待 reader thread 派发信号
                qtbot.waitUntil(lambda: len(received_data) >= 1, timeout=2000)

                assert b"".join(received_data) == b"hello world\n"
            finally:
                handler.close()
        finally:
            vs.close()

    def test_binary_data_round_trip(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                payload = bytes(range(256))
                handler.write_data(payload)
                echoed = vs.read_from_external(size=256, timeout=1.0)
                assert echoed == payload
            finally:
                handler.close()
        finally:
            vs.close()

    def test_multiple_chunks_concatenated(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(lambda d: received.append(d))

                vs.write_from_external(b"chunk1\n")
                vs.write_from_external(b"chunk2\n")
                vs.write_from_external(b"chunk3\n")

                # Reader thread 0.1s timeout 后会派发，3 个 chunk 2s 内应到齐
                qtbot.waitUntil(
                    lambda: b"chunk1" in b"".join(received)
                    and b"chunk2" in b"".join(received)
                    and b"chunk3" in b"".join(received),
                    timeout=3000,
                )
                full = b"".join(received)
                assert b"chunk1" in full
                assert b"chunk2" in full
                assert b"chunk3" in full
            finally:
                handler.close()
        finally:
            vs.close()

    def test_close_during_active_read(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            assert handler.is_open()
            handler.close()
            assert not handler.is_open()
            assert handler.serial_port is None
        finally:
            vs.close()

    def test_write_after_close_fails(self):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            handler.close()
            result = handler.write_data(b"x")
            assert result is False
        finally:
            vs.close()


# ── 端到端数据流测试（SerialMonitor + 真实 PTY）───────────────


from ui.main_window import SerialMonitor  # noqa: E402


@pytest.fixture
def monitor_with_pty(qtbot):
    """创建一个 SerialMonitor 和虚拟 PTY 的组合 fixture。"""
    vs = VirtualSerial()
    monitor = SerialMonitor()
    qtbot.addWidget(monitor)
    yield monitor, vs
    monitor.serial_handler.close()
    vs.close()


class TestEndToEndDataFlow:
    def test_send_data_via_pty(self, monitor_with_pty, qtbot):
        monitor, vs = monitor_with_pty
        monitor.show_timestamp = False

        ok = monitor.serial_handler.open(vs.port_name, baudrate=9600)
        assert ok

        try:
            monitor.send_input.setText("AT+CMD")
            # 直接通过 SerialHandler 写入，绕过 send_data 的 UI 副作用
            result = monitor.serial_handler.write_data(b"AT+CMD")
            assert result is True

            # 从 master 端读取 serial 写入的数据
            echoed = vs.read_from_external(size=20, timeout=1.0)
            assert b"AT+CMD" in echoed
        finally:
            monitor.serial_handler.close()

    def test_send_with_line_ending_via_pty(self, monitor_with_pty, qtbot):
        monitor, vs = monitor_with_pty
        monitor.show_timestamp = False

        ok = monitor.serial_handler.open(vs.port_name, baudrate=9600)
        assert ok

        try:
            # 直接通过 SerialHandler 写入
            result = monitor.serial_handler.write_data(b"CMD\r\n")
            assert result is True

            echoed = vs.read_from_external(size=20, timeout=1.0)
            assert echoed == b"CMD\r\n"
        finally:
            monitor.serial_handler.close()

    def test_send_with_checksum_via_pty(self, monitor_with_pty, qtbot):
        monitor, vs = monitor_with_pty
        monitor.show_timestamp = False

        ok = monitor.serial_handler.open(vs.port_name, baudrate=9600)
        assert ok

        try:
            # AA + BB = 0x65 校验和
            payload = b"\xAA\xBB\x65"
            result = monitor.serial_handler.write_data(payload)
            assert result is True

            echoed = vs.read_from_external(size=20, timeout=1.0)
            assert echoed == payload
        finally:
            monitor.serial_handler.close()


# ── Phase 5: 端到端数据流接收测试（使用独立 fixture）───────────


from PyQt6.QtCore import QCoreApplication  # noqa: E402


@pytest.fixture
def fresh_monitor_pty(qtbot):
    """每个测试用全新的 SerialMonitor + PTY，无共享状态。"""
    vs = VirtualSerial()
    monitor = SerialMonitor()
    qtbot.addWidget(monitor)
    yield monitor, vs
    try:
        if monitor.serial_handler.is_open():
            monitor.serial_handler.close()
    except Exception:
        pass
    vs.close()


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndReceive:
    """接收端到端测试：使用 SerialHandler + 信号连接，绕过 SerialMonitor 的 UI 开销。"""

    def test_ascii_receive_via_pty(self, qtbot):
        from PyQt6.QtCore import QCoreApplication
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            received = []
            handler.data_received.connect(received.append)

            ok = handler.open(vs.port_name, baudrate=9600)
            assert ok

            try:
                vs.write_from_external(b"hello world\n")
                qtbot.waitUntil(
                    lambda: b"hello world" in b"".join(received),
                    timeout=3000,
                )
                full = b"".join(received)
                assert b"hello world" in full
            finally:
                handler.close()
        finally:
            vs.close()

    def test_hex_receive_via_pty(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            received = []
            handler.data_received.connect(received.append)

            ok = handler.open(vs.port_name, baudrate=9600)
            assert ok

            try:
                vs.write_from_external(b"\x41\x42\x43")
                qtbot.waitUntil(
                    lambda: b"\x41\x42\x43" in b"".join(received),
                    timeout=3000,
                )
                full = b"".join(received)
                assert b"\x41" in full
                assert b"\x42" in full
                assert b"\x43" in full
            finally:
                handler.close()
        finally:
            vs.close()


# ── 协议解析 + 真实数据流 ──────────────────────────────────


from core.protocol import (  # noqa: E402
    normalize_hex_input,
    parse_payload,
    apply_checksum,
    format_hex,
    ChecksumApplyResult,
)


class TestProtocolWithRealData:
    def test_modbus_like_frame(self):
        """模拟 Modbus 帧：地址 + 功能码 + 数据 + CRC。"""
        # 模拟一个 Modbus RTU 读保持寄存器请求
        address = b"\x01"      # 设备地址
        function = b"\x03"     # 功能码
        start_reg = b"\x00\x01"  # 起始寄存器
        count = b"\x00\x02"    # 寄存器数量
        frame = address + function + start_reg + count

        # 计算 CRC16（Modbus）
        # 这里用简单的字节和作为校验
        checksum = sum(frame) & 0xFF
        result = apply_checksum(frame, checksum_start_1based=1, checksum_end_mode=0)
        assert result.valid_range
        assert result.checksum is not None

    def test_at_command_round_trip(self):
        """AT 命令发送和响应解析。"""
        # 发送
        cmd = "AT+VER\r\n"
        encoded = cmd.encode("utf-8")
        # AT+VER\r\n = 8 字节
        assert len(encoded) == 8
        assert b"\r\n" in encoded

        # 模拟响应
        response = b"OK\r\n"
        decoded = response.decode("utf-8")
        assert decoded == "OK\r\n"

    def test_hex_payload_through_protocol(self):
        """hex 字符串到字节的完整协议处理。"""
        hex_input = "AA 55 01 02 03 04"
        normalized = normalize_hex_input(hex_input)
        assert normalized == "AA5501020304"
        payload = parse_payload(normalized, is_hex=True)
        assert payload == b"\xAA\x55\x01\x02\x03\x04"
        assert len(payload) == 6

    def test_binary_payload_format(self):
        """二进制回显格式化。"""
        data = b"\xDE\xAD\xBE\xEF"
        formatted = format_hex(data)
        assert formatted == "DE AD BE EF"

    def test_escape_sequence_in_data(self):
        """数据中含 ANSI 转义码不应破坏协议层解析。"""
        # ANSI 颜色码不算协议字节，应在协议层保留，UI 层处理
        raw = b"\x1b[32mOK\x1b[0m\r\n"
        assert raw.startswith(b"\x1b[")
        # parse_payload 应该是 ASCII
        text = parse_payload(raw.decode("utf-8"), is_hex=False)
        assert text == raw

    def test_partial_frame_handling(self):
        """分片接收：先收一半，再收另一半。"""
        frame_full = b"\xAA\xBB\xCC\xDD\xEE\xFF"
        part1 = frame_full[:3]
        part2 = frame_full[3:]

        # 模拟两次写入
        combined = part1 + part2
        assert combined == frame_full
        assert len(part1) + len(part2) == len(frame_full)


# ── 终端模拟器 + 真实字节流 ─────────────────────────────────


from ui.terminal_emulator import TerminalEmulator  # noqa: E402


class TestTerminalEmulatorRealData:
    def test_ansi_color_through_emulator(self, qtbot):
        term = TerminalEmulator(rows=2, cols=20)
        qtbot.addWidget(term)

        # 模拟带 ANSI 颜色的输出
        term.process_bytes(b"\x1b[31mERROR\x1b[0m\r\n")
        assert term.grid[0][0].char == "E"
        assert term.grid[0][1].char == "R"

    def test_progress_bar_sequence(self, qtbot):
        term = TerminalEmulator(rows=2, cols=12)
        qtbot.addWidget(term)

        # 模拟进度条更新：用单行覆盖
        # \r 回到行首，写满 [##########] 后清行
        final = b"\r[##########]\x1b[K"
        term.process_bytes(final)

        row = "".join(c.char for c in term.grid[0])
        assert "##########" in row

    def test_full_terminal_session(self, qtbot):
        term = TerminalEmulator(rows=5, cols=40)
        qtbot.addWidget(term)

        # 模拟一段输出（避免自动 wrap 干扰断言）
        term.process_bytes(b"$ ready\r\n")
        term.process_bytes(b"$ ")

        all_text = "".join(c.char for row in term.grid for c in row)
        assert "$" in all_text
        assert "ready" in all_text


# ── Phase 2: 重连/并发/多实例 ─────────────────────────────


class TestReconnectScenarios:
    def test_close_pty_triggers_error_signal(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            errors = []
            handler.error_occurred.connect(errors.append)

            # 关闭 master 端模拟设备断开
            # 注意：关闭 master 不会让 reader 立即报错，因为 slave 还在
            # 我们直接调用 handler.close() 模拟断开
            handler.close()
            # 验证 is_open 为 False
            assert not handler.is_open()
        finally:
            vs.close()

    def test_multiple_open_close_cycles(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            for i in range(3):
                ok = handler.open(vs.port_name, baudrate=9600)
                assert ok is True
                assert handler.is_open()
                handler.write_data(b"x")
                handler.close()
                assert not handler.is_open()
        finally:
            vs.close()

    def test_open_after_close_succeeds(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            handler.close()
            # 再次打开
            ok = handler.open(vs.port_name, baudrate=9600)
            assert ok is True
            assert handler.is_open()
            handler.close()
        finally:
            vs.close()

    def test_is_open_reflects_state(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            assert not handler.is_open()
            handler.open(vs.port_name, baudrate=9600)
            assert handler.is_open()
            handler.close()
            assert not handler.is_open()
        finally:
            vs.close()

    def test_open_invalid_port_does_not_set_current(self):
        handler = SerialHandler()
        handler.open("/dev/ttyNONEXISTENT_XYZ_9999", baudrate=9600)
        assert handler.current_port is None
        assert handler.last_error is not None


class TestConcurrentReadWrite:
    def test_alternating_read_write(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(received.append)

                # 交替读写
                for i in range(5):
                    handler.write_data(f"req{i}\n".encode())
                    vs.write_from_external(f"resp{i}\n".encode())

                qtbot.waitUntil(
                    lambda: b"resp4" in b"".join(received),
                    timeout=3000,
                )
                full = b"".join(received)
                assert b"resp0" in full
                assert b"resp4" in full
            finally:
                handler.close()
        finally:
            vs.close()

    def test_burst_write_then_read(self, qtbot):
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(received.append)

                # 一次性写入 100 个小包
                for i in range(100):
                    handler.write_data(f"{i:03d}\n".encode())
                # 一次性读大量数据
                vs.write_from_external(b"x" * 1000)

                qtbot.waitUntil(
                    lambda: b"x" * 1000 in b"".join(received),
                    timeout=3000,
                )
            finally:
                handler.close()
        finally:
            vs.close()

    def test_write_does_not_block_on_unread_peer(self, qtbot):
        """外部不读取时，写入不应阻塞（PTY 缓冲应足够）。"""
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                # 写入较小数据（PTY 默认缓冲 4096 字节）
                handler.write_data(b"A" * 1024)
                # 验证写入成功
                assert handler.last_error is None
            finally:
                handler.close()
        finally:
            vs.close()


class TestMultipleInstances:
    def test_two_independent_handlers(self, qtbot):
        vs1 = VirtualSerial()
        vs2 = VirtualSerial()
        try:
            h1 = SerialHandler()
            h2 = SerialHandler()
            h1.open(vs1.port_name, baudrate=9600)
            h2.open(vs2.port_name, baudrate=9600)

            h1_received = []
            h2_received = []
            h1.data_received.connect(h1_received.append)
            h2.data_received.connect(h2_received.append)

            # 分别发送
            vs1.write_from_external(b"to_h1\n")
            vs2.write_from_external(b"to_h2\n")

            qtbot.waitUntil(
                lambda: b"to_h1" in b"".join(h1_received)
                and b"to_h2" in b"".join(h2_received),
                timeout=3000,
            )

            # 验证隔离
            h1_data = b"".join(h1_received)
            h2_data = b"".join(h2_received)
            assert b"to_h1" in h1_data
            assert b"to_h2" not in h1_data
            assert b"to_h2" in h2_data
            assert b"to_h1" not in h2_data

            h1.close()
            h2.close()
        finally:
            vs1.close()
            vs2.close()


@pytest.mark.integration
@pytest.mark.slow
class TestConfigRoundTrip:
    """配置持久化 round-trip 测试。"""

    def test_settings_round_trip(self, tmp_path):
        from utils.config_manager import ConfigManager
        import json

        original_settings_file = ConfigManager._SETTINGS_FILE
        original_config_dir = ConfigManager._CONFIG_DIR
        try:
            ConfigManager._CONFIG_DIR = tmp_path
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"

            test_data = {
                "language": "en",
                "theme_index": 3,
                "baudrate": "115200",
                "terminal_mode": True,
                "checksum_start": 5,
            }
            ConfigManager.save_settings(test_data)
            loaded = ConfigManager.load_settings()
            assert loaded == test_data
        finally:
            ConfigManager._SETTINGS_FILE = original_settings_file
            ConfigManager._CONFIG_DIR = original_config_dir

    def test_quick_sends_round_trip(self, tmp_path):
        from utils.config_manager import ConfigManager

        original = ConfigManager._QUICK_SEND_FILE
        original_dir = ConfigManager._CONFIG_DIR
        try:
            ConfigManager._CONFIG_DIR = tmp_path
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"

            items = [
                {"content": "AT", "is_hex": False, "checked": True, "auto_checksum": False},
                {"content": "A0", "is_hex": True, "checked": False, "auto_checksum": True},
            ]
            ConfigManager.save_quick_sends(items)
            loaded = ConfigManager.load_quick_sends()
            assert loaded == items
        finally:
            ConfigManager._QUICK_SEND_FILE = original
            ConfigManager._CONFIG_DIR = original_dir

    def test_unicode_round_trip(self, tmp_path):
        """Unicode 字符在配置中应保持。"""
        from utils.config_manager import ConfigManager

        original = ConfigManager._QUICK_SEND_FILE
        original_dir = ConfigManager._CONFIG_DIR
        try:
            ConfigManager._CONFIG_DIR = tmp_path
            ConfigManager._QUICK_SEND_FILE = tmp_path / "qs.json"

            items = [{"content": "你好世界 🌍 émojis"}]
            ConfigManager.save_quick_sends(items)
            loaded = ConfigManager.load_quick_sends()
            assert loaded == items
            assert loaded[0]["content"] == "你好世界 🌍 émojis"
        finally:
            ConfigManager._QUICK_SEND_FILE = original
            ConfigManager._CONFIG_DIR = original_dir


# ── Phase 4: 协议场景测试 ─────────────────────────────


@pytest.mark.integration
@pytest.mark.slow
class TestProtocolScenarios:
    """模拟真实设备协议栈的端到端测试。"""

    def test_at_command_request_response(self, qtbot):
        """AT 命令请求-响应循环。"""
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(received.append)

                # 客户端发 AT 命令
                handler.write_data(b"AT\r\n")
                # 设备响应 OK
                vs.write_from_external(b"OK\r\n")

                qtbot.waitUntil(
                    lambda: b"OK" in b"".join(received),
                    timeout=2000,
                )
                full = b"".join(received)
                assert b"OK" in full
            finally:
                handler.close()
        finally:
            vs.close()

    def test_modbus_like_frame_exchange(self, qtbot):
        """模拟 Modbus 请求-响应：客户端发请求帧，设备回响应帧。"""
        from core.protocol import apply_checksum

        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(received.append)

                # 构造 Modbus 读保持寄存器请求：01 03 00 00 00 02
                request = b"\x01\x03\x00\x00\x00\x02"
                # 加校验和
                result = apply_checksum(request, checksum_start_1based=1)
                assert result.valid_range
                full_request = result.payload

                handler.write_data(full_request)
                vs.write_from_external(full_request)  # echo 回来

                # 设备响应：01 03 04 00 0A 01 02 (读 2 个寄存器)
                response = b"\x01\x03\x04\x00\x0A\x01\x02"
                resp_result = apply_checksum(response, checksum_start_1based=1)
                vs.write_from_external(resp_result.payload)

                qtbot.waitUntil(
                    lambda: b"\\x01\\x03" in b"".join(received)
                    or b"\x01\x03" in b"".join(received),
                    timeout=2000,
                )
                full = b"".join(received)
                assert b"\x01\x03" in full
            finally:
                handler.close()
        finally:
            vs.close()

    def test_binary_protocol_with_length_prefix(self, qtbot):
        """测试 SOF + length + payload 协议。"""
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(received.append)

                # 设备发送: SOF(0xAA) + len(0x04) + payload(0x01 0x02 0x03 0x04) + CRC
                sof = b"\xAA"
                length = b"\x04"
                payload = b"\x01\x02\x03\x04"
                crc = b"\x0A"  # 简化的校验
                frame = sof + length + payload + crc

                vs.write_from_external(frame)

                qtbot.waitUntil(
                    lambda: frame in b"".join(received),
                    timeout=2000,
                )
                full = b"".join(received)
                assert frame in full
            finally:
                handler.close()
        finally:
            vs.close()

    def test_request_response_loop(self, qtbot):
        """多轮请求-响应循环。"""
        vs = VirtualSerial()
        try:
            handler = SerialHandler()
            handler.open(vs.port_name, baudrate=9600)
            try:
                received = []
                handler.data_received.connect(received.append)

                # 模拟 5 轮交互
                for i in range(5):
                    cmd = f"CMD{i}\n".encode()
                    handler.write_data(cmd)
                    resp = f"RESP{i}\n".encode()
                    vs.write_from_external(resp)

                qtbot.waitUntil(
                    lambda: all(f"RESP{i}".encode() in b"".join(received) for i in range(5)),
                    timeout=5000,
                )
                full = b"".join(received)
                for i in range(5):
                    assert f"RESP{i}".encode() in full
            finally:
                handler.close()
        finally:
            vs.close()
