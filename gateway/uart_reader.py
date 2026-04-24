import asyncio
import json
import logging

import serial
import serial.serialutil

from config import Config

logger = logging.getLogger(__name__)

_MAX_FRAME_BYTES = 512
_RECONNECT_INTERVAL_SEC = 5


class UartReader:
    def __init__(self, config: Config, queue: asyncio.Queue,
                 serial_port: serial.Serial) -> None:
        self._config = config
        self._queue = queue
        self._serial = serial_port

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                await loop.run_in_executor(None, self._open)
                logger.info(json.dumps({"event": "uart_connected",
                                        "port": self._config.uart_port}))
                await self._read_loop(loop)
            except (serial.serialutil.SerialException, OSError) as exc:
                logger.warning(json.dumps({"event": "uart_disconnected",
                                           "reason": str(exc)}))
                await asyncio.sleep(_RECONNECT_INTERVAL_SEC)

    def _open(self) -> None:
        if self._serial.is_open:
            self._serial.close()
        self._serial.port     = self._config.uart_port
        self._serial.baudrate = self._config.uart_baudrate
        self._serial.timeout  = 1
        self._serial.open()

    async def _read_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        buf = bytearray()
        while True:
            chunk = await loop.run_in_executor(None, self._serial.readline)
            if not chunk:
                continue
            buf.extend(chunk)

            if b"\n" not in buf:
                if len(buf) > _MAX_FRAME_BYTES:
                    logger.warning(json.dumps({"event": "uart_parse_error",
                                               "reason": "frame_too_long",
                                               "raw": buf[:64].decode("utf-8", errors="replace")}))
                    buf.clear()
                continue

            idx = buf.index(b"\n")
            raw = buf[:idx]
            buf = buf[idx + 1:]

            frame = self._parse_frame(bytes(raw))
            if frame is not None:
                await self._queue.put(frame)

    def _parse_frame(self, raw: bytes) -> dict | None:
        if len(raw) > _MAX_FRAME_BYTES:
            logger.warning(json.dumps({"event": "uart_parse_error",
                                       "reason": "frame_too_long"}))
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(json.dumps({"event": "uart_parse_error",
                                       "reason": str(exc),
                                       "raw": raw[:64].decode("utf-8", errors="replace")}))
            return None
