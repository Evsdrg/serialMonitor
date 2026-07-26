"""
串口通信处理模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import serial
import serial.tools.list_ports
from PyQt6.QtCore import QThread, pyqtSignal

from core.transport import (
    DisconnectReason,
    TransportHandler,
    TransportOperation,
    TransportState,
)

logger = logging.getLogger(__name__)


class _SerialReadThread(QThread):
    """后台串口读取线程（阻塞读 + timeout 轮询退出）。"""

    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    session_data_received = pyqtSignal(object, bytes)
    session_error_occurred = pyqtSignal(object, str)

    def __init__(self, serial_port: serial.Serial) -> None:
        super().__init__()
        self._serial_port = serial_port
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:  # noqa: D401
        while self._running:
            try:
                data = self._serial_port.read(4096)
                if data:
                    self.data_received.emit(data)
                    self.session_data_received.emit(self, data)
            except (OSError, serial.SerialException) as e:
                self.error_occurred.emit(str(e))
                self.session_error_occurred.emit(self, str(e))
                return
            except Exception as e:
                logger.exception("Unexpected error in serial read thread")
                self.error_occurred.emit(str(e))
                self.session_error_occurred.emit(self, str(e))
                return


class _SerialWriteThread(QThread):
    """后台串口写入线程（FIFO 队列，避免阻塞 GUI）。"""

    session_error_occurred = pyqtSignal(object, str)

    def __init__(self, serial_port: serial.Serial) -> None:
        super().__init__()
        self._serial_port = serial_port
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._idle = threading.Event()
        self._idle.set()

    def enqueue(self, data: bytes) -> None:
        with self._lock:
            self._pending += len(data)
        self._idle.clear()
        self._queue.put(data)

    def pending_bytes(self) -> int:
        with self._lock:
            return self._pending

    def wait_idle(self, timeout_s: float) -> bool:
        return self._idle.wait(timeout_s)

    def stop(self, drain: bool = False) -> None:
        if not drain:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            with self._lock:
                self._pending = 0
            self._idle.set()
        self._queue.put(None)

    def run(self) -> None:  # noqa: D401
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                written = self._serial_port.write(item)
                if written is not None and written != len(item):
                    self.session_error_occurred.emit(
                        self,
                        f"Serial write accepted {written} of {len(item)} bytes",
                    )
            except (OSError, serial.SerialException) as e:
                self.session_error_occurred.emit(self, str(e))
            except Exception as e:  # noqa: BLE001
                logger.exception("Unexpected error in serial write thread")
                self.session_error_occurred.emit(self, str(e))
            finally:
                with self._lock:
                    self._pending = max(0, self._pending - len(item))
                    drained = self._pending == 0 and self._queue.empty()
                if drained:
                    self._idle.set()
        self._idle.set()


class SerialHandler(TransportHandler):
    """串口通信处理类"""

    _WRITE_ACK_SECONDS = 0.05
    _WRITE_DRAIN_SECONDS = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.serial_port: Optional[serial.Serial] = None
        self.current_port: Optional[str] = None
        self._target_port: Optional[str] = None
        self._reader_thread: Optional[_SerialReadThread] = None
        self._orphan_readers: list[_SerialReadThread] = []
        self._writer_thread: Optional[_SerialWriteThread] = None

    @property
    def endpoint(self) -> str:
        return self.current_port or self._target_port or ""

    @staticmethod
    def get_available_ports() -> list[str]:
        """获取可用的串口列表，ttyUSB 优先。"""
        ports = serial.tools.list_ports.comports()
        sorted_ports = sorted(
            ports,
            key=lambda p: (
                0 if "ttyUSB" in p.device else 1 if "ttyACM" in p.device else 2
            ),
        )
        return [p.device for p in sorted_ports]

    def is_open(self) -> bool:
        """检查串口是否打开。"""
        return (
            self._state is TransportState.CONNECTED
            and self.serial_port is not None
            and self.serial_port.is_open
        )

    def open(
        self,
        port: str,
        baudrate: int | str = 115200,
        parity: str = "N",
        databits: int | str = 8,
        stopbits: float | str = 1,
        dtr: bool = True,
        rts: bool = True,
    ) -> bool:
        """打开串口。

        Args:
            port: 端口名称。
            baudrate: 波特率。
            parity: 校验位 ('N', 'E', 'O', 'None', 'Even', 'Odd')。
            databits: 数据位 (5, 6, 7, 8)。
            stopbits: 停止位 (1, 1.5, 2)。

        Returns:
            是否成功打开。
        """
        if self.is_open():
            return True
        self._target_port = port
        self._transition(TransportState.CONNECTING)

        parity_map: dict[str, str] = {
            "N": serial.PARITY_NONE,
            "None": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "Even": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "Odd": serial.PARITY_ODD,
        }

        stopbits_map: dict[str | float, float] = {
            1: serial.STOPBITS_ONE,
            "1": serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            "1.5": serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO,
            "2": serial.STOPBITS_TWO,
        }

        try:
            serial_port = serial.Serial(
                port=None,
                baudrate=int(baudrate),
                parity=parity_map.get(parity, serial.PARITY_NONE),
                stopbits=stopbits_map.get(stopbits, serial.STOPBITS_ONE),
                bytesize=int(databits),
                timeout=0.1,
                write_timeout=5.0,
            )
            serial_port.dtr = dtr
            serial_port.rts = rts
            serial_port.port = port
            serial_port.open()
            self.serial_port = serial_port
            self.current_port = port
            self._target_port = None
            self.last_error = None

            self._start_reader()
            self._transition(TransportState.CONNECTED)
            return True
        except (OSError, ValueError, serial.SerialException) as e:
            self._emit_error(TransportOperation.CONNECT, str(e))
            self._transition(
                TransportState.DISCONNECTED, DisconnectReason.CONNECT_FAILED
            )
            self._target_port = None
            return False

    def _start_reader(self) -> None:
        if not self._stop_reader():
            # 旧线程无法停止时必须脱离，否则会被静默覆盖并泄漏
            self._detach_reader()
        if not self.serial_port:
            return
        self._reader_thread = _SerialReadThread(self.serial_port)
        self._reader_thread.session_data_received.connect(self._on_reader_data)
        self._reader_thread.session_error_occurred.connect(self._on_reader_error)
        self._reader_thread.start()

    def _stop_reader(self, timeout_ms: int = 1000) -> bool:
        if self._reader_thread is None:
            return True

        self._reader_thread.stop()
        if self.serial_port is not None:
            cancel_read = getattr(self.serial_port, "cancel_read", None)
            if callable(cancel_read):
                try:
                    cancel_read()
                except (OSError, serial.SerialException) as e:
                    logger.debug("Failed to cancel serial read: %s", e)

        if not self._reader_thread.wait(timeout_ms):
            self.last_error = "Serial reader thread did not stop"
            logger.error(self.last_error)
            return False

        self._reader_thread = None
        return True

    def _start_writer(self) -> None:
        self._stop_writer(drain=False)
        if not self.serial_port:
            return
        self._writer_thread = _SerialWriteThread(self.serial_port)
        self._writer_thread.session_error_occurred.connect(self._on_writer_error)
        self._writer_thread.start()

    def _stop_writer(self, drain: bool, timeout_ms: int = 1000) -> None:
        writer = self._writer_thread
        if writer is None:
            return
        if drain:
            writer.wait_idle(self._WRITE_DRAIN_SECONDS)
        writer.stop(drain=drain)
        if not writer.wait(timeout_ms):
            logger.warning("Serial writer thread did not stop")
        try:
            writer.session_error_occurred.disconnect(self._on_writer_error)
        except (TypeError, RuntimeError):
            pass
        self._writer_thread = None

    def _on_writer_error(self, writer: object, message: str) -> None:
        if writer is not self._writer_thread:
            return
        self._emit_error(TransportOperation.WRITE, message)

    def _detach_reader(self) -> None:
        """放弃无法停止的读取线程：断开信号并保留引用直到它自行结束。"""
        reader = self._reader_thread
        if reader is None:
            return
        for signal, slot in (
            (reader.session_data_received, self._on_reader_data),
            (reader.session_error_occurred, self._on_reader_error),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        try:
            reader.stop()
        except RuntimeError:
            pass
        self._orphan_readers.append(reader)
        try:
            reader.finished.connect(
                lambda r=reader: self._forget_orphan_reader(r)
            )
        except (AttributeError, RuntimeError):
            pass
        self._reader_thread = None

    def _forget_orphan_reader(self, reader: object) -> None:
        if reader in self._orphan_readers:
            self._orphan_readers.remove(reader)

    def _on_reader_data(self, reader: object, data: bytes) -> None:
        if reader is self._reader_thread and self._state is TransportState.CONNECTED:
            self.data_received.emit(data)

    def _on_reader_error(
        self, reader_or_message: object, message: str | None = None
    ) -> None:
        if message is None:
            reader = self._reader_thread
            message = str(reader_or_message)
        else:
            reader = reader_or_message
        if reader is not self._reader_thread:
            return
        self._emit_error(TransportOperation.READ, message)
        self.close(reason=DisconnectReason.IO_ERROR)

    def close(
        self, reason: DisconnectReason = DisconnectReason.USER
    ) -> bool:
        """关闭串口。"""
        if self._state is TransportState.DISCONNECTED and self.serial_port is None:
            return True
        self._transition(TransportState.CLOSING)
        # 用户主动断开时排空写队列，应用退出/故障关闭则直接丢弃
        self._stop_writer(drain=reason is DisconnectReason.USER)
        stopped = self._stop_reader()

        # 关闭端口本身就是解阻塞读取的手段，无论线程是否已停止都必须执行
        if self.serial_port:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
            except (OSError, serial.SerialException) as e:
                logger.warning("Error closing serial port: %s", e)

            self.serial_port = None

        if not stopped and not self._stop_reader(500):
            self._detach_reader()
            if self.last_error:
                self._emit_error(TransportOperation.SHUTDOWN, self.last_error)

        self._transition(TransportState.DISCONNECTED, reason)
        return True

    def shutdown(self, timeout_ms: int = 3000) -> bool:
        return self.close(reason=DisconnectReason.SHUTDOWN)

    def set_dtr(self, level: bool) -> bool:
        """设置 DTR 引脚电平。"""
        if not self.is_open():
            return False
        try:
            self.serial_port.dtr = level  # type: ignore[union-attr]
        except (OSError, serial.SerialException) as e:
            self._emit_error(TransportOperation.CONTROL, str(e))
            return False
        return True

    def set_rts(self, level: bool) -> bool:
        """设置 RTS 引脚电平。"""
        if not self.is_open():
            return False
        try:
            self.serial_port.rts = level  # type: ignore[union-attr]
        except (OSError, serial.SerialException) as e:
            self._emit_error(TransportOperation.CONTROL, str(e))
            return False
        return True

    def write_data(self, data: bytes) -> bool:
        """把数据交给写入线程。

        Args:
            data: 要发送的字节数据。

        Returns:
            是否已被接受（写入结果通过 transport_error 异步反馈）。
        """
        if not self.is_open():
            return False
        if self._writer_thread is None:
            # 首次写入时才启动写线程，只读会话不占用线程
            self._start_writer()
        if self._writer_thread is None:
            return False

        self.last_error = None
        self._writer_thread.enqueue(data)
        # 短暂等待，常见的小报文可在返回前完成，从而如实报告 SENT
        self._writer_thread.wait_idle(self._WRITE_ACK_SECONDS)
        return True

    def has_pending_writes(self) -> bool:
        """是否仍有数据排队等待写出。"""
        writer = self._writer_thread
        return writer is not None and writer.pending_bytes() > 0

    def check_device_exists(self) -> bool:
        """检查当前连接的设备是否还存在。"""
        if not self.current_port:
            return False
        return self.current_port in self.get_available_ports()

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """计算校验和 (所有字节之和 mod 256)。

        Args:
            data: bytes 数据。

        Returns:
            校验和值 (0-255)。
        """
        return sum(data) & 0xFF
