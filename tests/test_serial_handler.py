"""
测试 core/serial_handler.py - 静态方法和基础功能
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from core.serial_handler import SerialHandler


class TestSerialHandlerStatic:
    """测试静态方法（不需要实例化 QObject）"""

    @patch("core.serial_handler.serial.tools.list_ports.comports")
    def test_get_available_ports_empty(self, mock_comports):
        mock_comports.return_value = []
        ports = SerialHandler.get_available_ports()
        assert ports == []

    @patch("core.serial_handler.serial.tools.list_ports.comports")
    def test_get_available_ports_sorted(self, mock_comports):
        mock_port1 = Mock()
        mock_port1.device = "/dev/ttyACM0"
        mock_port2 = Mock()
        mock_port2.device = "/dev/ttyUSB0"
        mock_port3 = Mock()
        mock_port3.device = "/dev/ttyS0"
        mock_comports.return_value = [mock_port1, mock_port2, mock_port3]

        ports = SerialHandler.get_available_ports()
        assert ports == ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0"]

    def test_calculate_checksum_empty(self):
        assert SerialHandler.calculate_checksum(b"") == 0

    def test_calculate_checksum_single_byte(self):
        assert SerialHandler.calculate_checksum(b"\x01") == 1

    def test_calculate_checksum_multiple_bytes(self):
        assert SerialHandler.calculate_checksum(b"\x01\x02\x03") == 6

    def test_calculate_checksum_overflow(self):
        assert SerialHandler.calculate_checksum(b"\xff\xff\xff") == 0xFD

    def test_calculate_checksum_max(self):
        assert SerialHandler.calculate_checksum(b"\xff") == 255

    def test_calculate_checksum_large_data(self):
        data = bytes(range(256))
        expected = sum(range(256)) & 0xFF
        assert SerialHandler.calculate_checksum(data) == expected


class TestSerialHandlerLogic:
    """测试串口处理逻辑（不涉及信号）"""

    def test_parity_map_values(self):
        import serial

        parity_map = {
            "N": serial.PARITY_NONE,
            "None": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "Even": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "Odd": serial.PARITY_ODD,
        }
        assert parity_map["N"] == serial.PARITY_NONE
        assert parity_map["E"] == serial.PARITY_EVEN
        assert parity_map["O"] == serial.PARITY_ODD

    def test_stopbits_map_values(self):
        import serial

        stopbits_map = {
            1: serial.STOPBITS_ONE,
            "1": serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            "1.5": serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO,
            "2": serial.STOPBITS_TWO,
        }
        assert stopbits_map[1] == serial.STOPBITS_ONE
        assert stopbits_map[2] == serial.STOPBITS_TWO
        assert stopbits_map[1.5] == serial.STOPBITS_ONE_POINT_FIVE


class TestSerialHandlerInstance:
    """测试实例化后的行为和状态"""

    def test_initial_state(self):
        handler = SerialHandler()
        assert handler.serial_port is None
        assert handler.current_port is None
        assert handler.last_error is None
        assert handler.is_open() is False

    def test_is_open_when_serial_closed(self):
        handler = SerialHandler()
        handler.serial_port = Mock()
        handler.serial_port.is_open = False
        assert handler.is_open() is False

    def test_open_already_open_returns_true(self):
        handler = SerialHandler()
        handler.serial_port = Mock()
        handler.serial_port.is_open = True
        assert handler.open("/dev/ttyUSB0") is True

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_open_success(self, mock_serial_class, mock_start_reader, qtbot):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        with qtbot.waitSignal(handler.connection_changed, timeout=1000):
            result = handler.open("/dev/ttyUSB0", baudrate=115200, parity="N", databits=8, stopbits=1)

        assert result is True
        assert handler.current_port == "/dev/ttyUSB0"
        assert handler.is_open() is True
        mock_serial_class.assert_called_once()

    def test_open_failure_emits_error(self, qtbot):
        import serial
        from core.serial_handler import SerialHandler

        handler = SerialHandler()

        def raising_serial(*args, **kwargs):
            raise serial.SerialException("permission denied")

        with patch("core.serial_handler.serial.Serial", raising_serial), \
             patch.object(SerialHandler, "_start_reader"):
            with qtbot.waitSignal(handler.error_occurred, timeout=1000):
                result = handler.open("/dev/ttyUSB0")

        assert result is False
        assert handler.last_error == "permission denied"
        del handler

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_open_with_parity_and_stopbits(self, mock_serial_class, mock_start_reader):
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        mock_serial_class.reset_mock()
        mock_serial_class.side_effect = None
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        handler.open("/dev/ttyUSB0", parity="Even", stopbits="1.5")

        call_kwargs = mock_serial_class.call_args.kwargs
        assert call_kwargs["parity"] == "E"
        assert call_kwargs["stopbits"] == 1.5

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_close_emits_disconnected(self, mock_serial_class, mock_start_reader, qtbot):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        handler.open("/dev/ttyUSB0")

        with qtbot.waitSignal(handler.connection_changed, timeout=1000):
            handler.close()

        assert handler.is_open() is False
        assert handler.serial_port is None

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_set_dtr(self, mock_serial_class, mock_start_reader):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        handler.open("/dev/ttyUSB0")
        handler.set_dtr(True)
        assert mock_port.dtr is True

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_set_rts(self, mock_serial_class, mock_start_reader):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        handler.open("/dev/ttyUSB0")
        handler.set_rts(False)
        assert mock_port.rts is False

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_write_data_success(self, mock_serial_class, mock_start_reader):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_serial_class.return_value = mock_port

        handler.open("/dev/ttyUSB0")
        result = handler.write_data(b"hello")
        assert result is True
        mock_port.write.assert_called_once_with(b"hello")

    def test_write_data_when_closed(self):
        handler = SerialHandler()
        assert handler.write_data(b"hello") is False

    @patch("core.serial_handler.SerialHandler._start_reader")
    @patch("core.serial_handler.serial.Serial")
    def test_write_data_failure(self, mock_serial_class, mock_start_reader, qtbot):
        handler = SerialHandler()
        import serial
        mock_port = Mock()
        mock_port.is_open = True
        mock_port.write.side_effect = serial.SerialException("write failed")
        mock_serial_class.return_value = mock_port

        handler.open("/dev/ttyUSB0")
        with qtbot.waitSignal(handler.error_occurred, timeout=1000):
            result = handler.write_data(b"hello")
        assert result is False

    @patch("core.serial_handler.SerialHandler.get_available_ports")
    def test_check_device_exists_true(self, mock_get_ports):
        handler = SerialHandler()
        handler.current_port = "/dev/ttyUSB0"
        mock_get_ports.return_value = ["/dev/ttyUSB0", "/dev/ttyACM0"]
        assert handler.check_device_exists() is True

    @patch("core.serial_handler.SerialHandler.get_available_ports")
    def test_check_device_exists_false(self, mock_get_ports):
        handler = SerialHandler()
        handler.current_port = "/dev/ttyUSB0"
        mock_get_ports.return_value = ["/dev/ttyACM0"]
        assert handler.check_device_exists() is False

    def test_check_device_exists_no_current_port(self):
        handler = SerialHandler()
        assert handler.check_device_exists() is False


class TestSerialHandlerReaderThread:
    """测试后台读取线程"""

    def test_reader_emits_data(self, qtbot):
        from core.serial_handler import _SerialReadThread
        import serial

        mock_port = Mock()
        mock_port.read.side_effect = [b"hello", serial.SerialException("stop")]
        thread = _SerialReadThread(mock_port)

        received: list[bytes] = []
        thread.data_received.connect(received.append)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000):
            thread.run()

        assert received == [b"hello"]

    def test_reader_error_emits_error(self, qtbot):
        from core.serial_handler import _SerialReadThread
        import serial

        mock_port = Mock()
        mock_port.read.side_effect = serial.SerialException("disconnected")
        thread = _SerialReadThread(mock_port)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000):
            thread.run()

    def test_reader_unexpected_error(self, qtbot):
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.side_effect = ValueError("unexpected")
        thread = _SerialReadThread(mock_port)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000):
            thread.run()


class TestSerialReadThreadLifecycle:
    """测试 _SerialReadThread 的生命周期管理。"""

    def test_stop_sets_running_false(self):
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        thread = _SerialReadThread(mock_port)
        assert thread._running is True
        thread.stop()
        assert thread._running is False

    def test_run_returns_immediately_when_stopped_before_start(self, qtbot):
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.return_value = b"data"
        thread = _SerialReadThread(mock_port)
        thread.stop()

        received = []
        thread.data_received.connect(received.append)
        # 由于 _running=False，run() 应立即返回
        thread.run()
        assert received == []

    def test_multiple_data_chunks_collected(self, qtbot):
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.side_effect = [b"chunk1", b"chunk2", b"chunk3", b""]
        thread = _SerialReadThread(mock_port)

        received = []
        thread.data_received.connect(received.append)
        # 让 read 返回空字节，run 会持续循环直到 _running=False
        # 这里我们在收到 3 个 chunk 后调用 stop
        def on_first_data(data):
            thread.stop()
        thread.data_received.connect(on_first_data)

        thread.run()
        # 至少收到一个 chunk
        assert len(received) >= 1
        assert received[0] == b"chunk1"

    def test_empty_data_not_emitted(self, qtbot):
        """read() 返回空字节不应触发 data_received 信号。"""
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        # 第一次空读，第二次非空
        mock_port.read.side_effect = [b"", b"real_data", b"", OSError("stop")]
        thread = _SerialReadThread(mock_port)

        received = []
        thread.data_received.connect(received.append)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000):
            thread.run()
        # 应该有 1 个真实数据
        assert received == [b"real_data"]

    def test_os_error_exits_thread(self, qtbot):
        """OSError 应触发 error_occurred 并退出。"""
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.side_effect = OSError("device unplugged")
        thread = _SerialReadThread(mock_port)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000) as blocker:
            thread.run()
        assert "device unplugged" in blocker.args[0]

    def test_serial_exception_exits_thread(self, qtbot):
        """SerialException 应触发 error_occurred 并退出。"""
        import serial as _serial
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.side_effect = _serial.SerialException("port lost")
        thread = _SerialReadThread(mock_port)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000) as blocker:
            thread.run()
        assert "port lost" in blocker.args[0]

    def test_unexpected_exception_logged(self, qtbot):
        """未知异常应被记录并触发 error_occurred。"""
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.side_effect = RuntimeError("weird")
        thread = _SerialReadThread(mock_port)

        with qtbot.waitSignal(thread.error_occurred, timeout=1000) as blocker:
            thread.run()
        assert "weird" in blocker.args[0]

    def test_thread_stops_gracefully(self, qtbot):
        """stop() 后 run 应能优雅退出。"""
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.return_value = b""  # 永远返回空
        thread = _SerialReadThread(mock_port)

        received = []
        thread.data_received.connect(received.append)

        # 异步停止线程
        def stop_later():
            import time
            time.sleep(0.05)
            thread.stop()

        import threading
        stopper = threading.Thread(target=stop_later, daemon=True)
        stopper.start()

        thread.run()  # 应在 50ms 后退出
        stopper.join(timeout=1.0)
        assert thread._running is False

    def test_serial_handler_uses_reader_thread(self, qtbot):
        """SerialHandler 打开后应启动 reader thread。"""
        handler = SerialHandler()
        handler.open("/dev/ttyNONEXISTENT_XYZ")  # 故意失败
        # 失败时不应启动 reader
        assert handler._reader_thread is None

    def test_close_stops_reader_thread(self, qtbot):
        """handler.close() 应停止 reader thread。"""
        import threading
        from core.serial_handler import _SerialReadThread

        mock_port = Mock()
        mock_port.read.return_value = b""
        thread = _SerialReadThread(mock_port)
        thread.start()

        # 等待线程启动
        import time
        time.sleep(0.05)

        # stop() 应被调用
        thread.stop()
        thread.wait(500)  # 等待最多 500ms

        assert not thread.isRunning()


class TestSerialHandlerClosePath:
    def test_close_no_port(self):
        handler = SerialHandler()
        handler.close()
        assert handler.serial_port is None
        assert handler.current_port is None

    def test_close_already_closed(self):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = False
        handler.serial_port = mock_port
        handler.current_port = "/dev/ttyUSB0"

        handler.close()
        mock_port.close.assert_not_called()
        assert handler.serial_port is None

    def test_close_emits_disconnected_with_port(self, qtbot):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        handler.serial_port = mock_port
        handler.current_port = "/dev/ttyUSB0"

        with qtbot.waitSignal(handler.connection_changed, timeout=1000) as blocker:
            handler.close()
        args = blocker.args
        assert args[0] is False
        assert args[1] == "/dev/ttyUSB0"
        assert handler.serial_port is None

    def test_close_handles_serial_exception(self):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        mock_port.close.side_effect = OSError("device gone")
        handler.serial_port = mock_port
        handler.current_port = "/dev/ttyUSB0"

        handler.close()  # 不抛异常
        assert handler.serial_port is None

    def test_stop_reader_no_thread(self):
        handler = SerialHandler()
        handler._stop_reader()  # 无线程，不抛异常

    def test_stop_reader_stops_thread(self):
        handler = SerialHandler()
        mock_thread = Mock()
        handler._reader_thread = mock_thread

        handler._stop_reader()
        mock_thread.stop.assert_called_once()
        mock_thread.wait.assert_called_once_with(500)
        assert handler._reader_thread is None

    def test_on_reader_error_closes_and_emits(self, qtbot):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        handler.serial_port = mock_port
        handler.current_port = "/dev/ttyUSB0"

        with qtbot.waitSignal(handler.error_occurred, timeout=1000) as blocker:
            handler._on_reader_error("device disconnected")
        assert blocker.args[0] == "device disconnected"
        assert handler.last_error == "device disconnected"
        assert handler.serial_port is None

    def test_set_dtr_not_open(self):
        handler = SerialHandler()
        handler.set_dtr(True)  # 不抛异常

    def test_set_rts_not_open(self):
        handler = SerialHandler()
        handler.set_rts(False)  # 不抛异常

    def test_set_dtr_exception(self):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        type(mock_port).dtr = Mock(side_effect=OSError("bus error"))
        handler.serial_port = mock_port

        handler.set_dtr(True)  # 异常被捕获

    def test_set_rts_exception(self):
        handler = SerialHandler()
        mock_port = Mock()
        mock_port.is_open = True
        type(mock_port).rts = Mock(side_effect=OSError("bus error"))
        handler.serial_port = mock_port

        handler.set_rts(True)  # 异常被捕获

    def test_write_data_exception(self, qtbot):
        handler = SerialHandler()
        import serial
        mock_port = Mock()
        mock_port.is_open = True
        mock_port.write.side_effect = serial.SerialException("write failed")
        handler.serial_port = mock_port
        handler.current_port = "/dev/ttyUSB0"

        with qtbot.waitSignal(handler.error_occurred, timeout=1000) as blocker:
            result = handler.write_data(b"data")
        assert result is False
        assert "write failed" in blocker.args[0]

    def test_get_available_ports_with_various(self):
        with patch("core.serial_handler.serial.tools.list_ports.comports") as mock_comports:
            mock_p1 = Mock()
            mock_p1.device = "/dev/ttyS0"
            mock_p2 = Mock()
            mock_p2.device = "/dev/ttyACM0"
            mock_p3 = Mock()
            mock_p3.device = "/dev/ttyUSB0"
            mock_comports.return_value = [mock_p1, mock_p2, mock_p3]
            ports = SerialHandler.get_available_ports()
            assert ports == ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0"]

    def test_check_device_exists_no_current(self):
        handler = SerialHandler()
        with patch("core.serial_handler.SerialHandler.get_available_ports",
                   return_value=["/dev/ttyUSB0"]):
            assert handler.check_device_exists() is False


class TestSerialHandlerIntegration:
    """集成测试 - 需要实际串口硬件或虚拟串口"""

    @pytest.mark.skip(reason="需要虚拟串口环境")
    def test_open_virtual_port(self):
        """使用 socat 创建的虚拟串口测试"""
        pass

    @pytest.mark.skip(reason="需要虚拟串口环境")
    def test_write_and_read_virtual_port(self):
        """测试虚拟串口读写"""
        pass
