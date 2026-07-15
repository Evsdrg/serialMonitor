"""Shared outbound payload preparation and delivery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from core.protocol import apply_checksum, parse_payload
from core.transport import WriteDisposition


class SendStatus(str, Enum):
    SENT = "sent"
    QUEUED = "queued"
    NOT_CONNECTED = "not_connected"
    INVALID_PAYLOAD = "invalid_payload"
    INVALID_CHECKSUM_RANGE = "invalid_checksum_range"
    WRITE_FAILED = "write_failed"


@dataclass(frozen=True)
class PayloadRequest:
    text: str = ""
    raw: bytes | None = None
    is_hex: bool = False
    line_ending: bytes = b""
    auto_checksum: bool = False
    checksum_start: int = 1
    checksum_end_mode: int = 0


@dataclass(frozen=True)
class SendResult:
    status: SendStatus
    payload: bytes = b""
    checksum: int | None = None

    @property
    def sent(self) -> bool:
        return self.status is SendStatus.SENT

    @property
    def accepted(self) -> bool:
        return self.status in (SendStatus.SENT, SendStatus.QUEUED)


class PayloadSender:
    def __init__(
        self,
        writer: Callable[[bytes], bool | WriteDisposition],
        is_connected: Callable[[], bool],
    ) -> None:
        self._writer = writer
        self._is_connected = is_connected

    def send(self, request: PayloadRequest) -> SendResult:
        if not self._is_connected():
            return SendResult(SendStatus.NOT_CONNECTED)

        if request.raw is not None:
            payload = request.raw
        else:
            try:
                payload = parse_payload(request.text, is_hex=request.is_hex)
            except ValueError:
                return SendResult(SendStatus.INVALID_PAYLOAD)

        payload += request.line_ending

        checksum = None
        if request.auto_checksum:
            checksum_result = apply_checksum(
                payload,
                checksum_start_1based=request.checksum_start,
                checksum_end_mode=request.checksum_end_mode,
            )
            if not checksum_result.valid_range:
                return SendResult(
                    SendStatus.INVALID_CHECKSUM_RANGE, payload=payload
                )
            payload = checksum_result.payload
            checksum = checksum_result.checksum

        disposition = self._writer(payload)
        if disposition is WriteDisposition.QUEUED:
            return SendResult(SendStatus.QUEUED, payload=payload, checksum=checksum)
        if disposition is WriteDisposition.REJECTED or not disposition:
            return SendResult(SendStatus.WRITE_FAILED, payload=payload)
        return SendResult(SendStatus.SENT, payload=payload, checksum=checksum)
