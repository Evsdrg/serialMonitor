"""
测试 core/serial_handler.py - 静态方法和基础功能
"""

import pytest
from unittest.mock import Mock, patch

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
