"""
串口通信处理模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
import serial
import serial.tools.list_ports
from PyQt6.QtCore import QObject, QThread, pyqtSignal


class _SerialReadThread(QThread):
    """后台串口读取线程（阻塞读 + timeout 轮询退出）。"""

    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)

    def __init__(self, serial_port):
        super().__init__()
        self._serial_port = serial_port
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                data = self._serial_port.read(4096)
                if data:
                    self.data_received.emit(data)
            except (OSError, serial.SerialException) as e:
                self.error_occurred.emit(str(e))
                return
            except Exception as e:
                self.error_occurred.emit(str(e))
                return


class SerialHandler(QObject):
    """串口通信处理类"""
    
    # 信号定义
    data_received = pyqtSignal(bytes)  # 收到数据
    connection_changed = pyqtSignal(bool, str)  # 连接状态改变 (is_connected, port_name)
    error_occurred = pyqtSignal(str)  # 发生错误
    
    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.current_port = None
        self.last_error = None
        self._reader_thread = None
    
    @staticmethod
    def get_available_ports():
        """获取可用的串口列表，ttyUSB优先"""
        ports = serial.tools.list_ports.comports()
        sorted_ports = sorted(ports, key=lambda p: (
            0 if 'ttyUSB' in p.device else
            1 if 'ttyACM' in p.device else
            2
        ))
        return [p.device for p in sorted_ports]
    
    def is_open(self):
        """检查串口是否打开"""
        return self.serial_port is not None and self.serial_port.is_open
    
    def open(self, port, baudrate=115200, parity='N', databits=8, stopbits=1):
        """
        打开串口
        
        Args:
            port: 端口名称
            baudrate: 波特率
            parity: 校验位 ('N', 'E', 'O')
            databits: 数据位 (5, 6, 7, 8)
            stopbits: 停止位 (1, 1.5, 2)
        """
        if self.is_open():
            return True
        
        # 转换参数
        parity_map = {
            'N': serial.PARITY_NONE,
            'None': serial.PARITY_NONE,
            'E': serial.PARITY_EVEN,
            'Even': serial.PARITY_EVEN,
            'O': serial.PARITY_ODD,
            'Odd': serial.PARITY_ODD
        }
        
        stopbits_map = {
            1: serial.STOPBITS_ONE,
            '1': serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            '1.5': serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO,
            '2': serial.STOPBITS_TWO
        }
        
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=int(baudrate),
                parity=parity_map.get(parity, serial.PARITY_NONE),
                stopbits=stopbits_map.get(stopbits, serial.STOPBITS_ONE),
                bytesize=int(databits),
                timeout=0.1  # 线程内阻塞读，便于退出
            )
            self.current_port = port
            self.last_error = None

            # 启动后台读取线程
            self._start_reader()

            self.connection_changed.emit(True, port)
            return True
        except Exception as e:
            self.last_error = str(e)
            self.error_occurred.emit(str(e))
            return False

    def _start_reader(self):
        self._stop_reader()
        if not self.serial_port:
            return
        self._reader_thread = _SerialReadThread(self.serial_port)
        self._reader_thread.data_received.connect(self.data_received)
        self._reader_thread.error_occurred.connect(self._on_reader_error)
        self._reader_thread.start()

    def _stop_reader(self):
        if self._reader_thread is None:
            return
        try:
            self._reader_thread.stop()
            self._reader_thread.wait(500)
        finally:
            self._reader_thread = None

    def _on_reader_error(self, message: str):
        self.last_error = message
        # reader 出错时认为连接已失效
        self.close()
        self.error_occurred.emit(message)
    
    def close(self):
        """关闭串口"""
        self._stop_reader()
        if self.serial_port:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
            except:
                pass
            
            port = self.current_port
            self.serial_port = None
            self.connection_changed.emit(False, port or '')

    def set_dtr(self, level: bool):
        """设置 DTR 引脚电平"""
        if self.is_open():
            try:
                self.serial_port.dtr = level
            except:
                pass

    def set_rts(self, level: bool):
        """设置 RTS 引脚电平"""
        if self.is_open():
            try:
                self.serial_port.rts = level
            except:
                pass
    
    def read_data(self):
        """
        读取串口数据
        
        Returns:
            bytes or None
        """
        if not self.is_open():
            return None
        
        try:
            if self.serial_port.in_waiting > 0:
                return self.serial_port.read_all()
        except (OSError, serial.SerialException) as e:
            self.last_error = str(e)
            self.close()
            self.error_occurred.emit(str(e))
        except Exception as e:
            self.last_error = str(e)
            self.error_occurred.emit(str(e))
        
        return None
    
    def write_data(self, data):
        """
        写入数据到串口
        
        Args:
            data: bytes 数据
            
        Returns:
            bool: 是否成功
        """
        if not self.is_open():
            return False
        
        try:
            self.serial_port.write(data)
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = str(e)
            self.error_occurred.emit(str(e))
            return False
    
    def check_device_exists(self):
        """检查当前连接的设备是否还存在"""
        if not self.current_port:
            return False
        return self.current_port in self.get_available_ports()
    
    @staticmethod
    def calculate_checksum(data):
        """
        计算校验和 (所有字节之和 mod 256)
        
        Args:
            data: bytes 数据
            
        Returns:
            int: 校验和值 (0-255)
        """
        return sum(data) & 0xFF
