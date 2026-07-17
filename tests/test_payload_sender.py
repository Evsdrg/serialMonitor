from unittest.mock import Mock

from core.payload_sender import (
    PayloadRequest,
    PayloadSender,
    SendStatus,
)
from core.transport import WriteDisposition


def test_not_connected_rejects_before_parsing():
    writer = Mock()
    sender = PayloadSender(writer, lambda: False)

    result = sender.send(PayloadRequest(text="not hex", is_hex=True))

    assert result.status is SendStatus.NOT_CONNECTED
    writer.assert_not_called()


def test_invalid_hex_is_reported_without_writing():
    writer = Mock()
    sender = PayloadSender(writer, lambda: True)

    result = sender.send(PayloadRequest(text="0G", is_hex=True))

    assert result.status is SendStatus.INVALID_PAYLOAD
    writer.assert_not_called()


def test_newline_is_applied_before_checksum():
    writer = Mock(return_value=True)
    sender = PayloadSender(writer, lambda: True)

    result = sender.send(
        PayloadRequest(
            text="A",
            line_ending=b"\n",
            auto_checksum=True,
            checksum_start=1,
        )
    )

    assert result.status is SendStatus.SENT
    assert result.payload == b"A\nK"
    writer.assert_called_once_with(b"A\nK")


def test_invalid_checksum_range_does_not_write():
    writer = Mock()
    sender = PayloadSender(writer, lambda: True)

    result = sender.send(
        PayloadRequest(text="A", auto_checksum=True, checksum_start=2)
    )

    assert result.status is SendStatus.INVALID_CHECKSUM_RANGE
    writer.assert_not_called()


def test_raw_terminal_bytes_are_not_transformed():
    writer = Mock(return_value=True)
    sender = PayloadSender(writer, lambda: True)

    result = sender.send(PayloadRequest(raw=b"\x00\xff\r"))

    assert result.status is SendStatus.SENT
    assert result.payload == b"\x00\xff\r"


def test_write_rejection_is_reported():
    sender = PayloadSender(Mock(return_value=False), lambda: True)

    result = sender.send(PayloadRequest(text="hello"))

    assert result.status is SendStatus.WRITE_FAILED


def test_async_writer_reports_queue_acceptance_not_delivery():
    sender = PayloadSender(
        Mock(return_value=WriteDisposition.QUEUED), lambda: True
    )

    result = sender.send(PayloadRequest(text="hello"))

    assert result.status is SendStatus.QUEUED
    assert result.accepted is True
    assert result.sent is False
