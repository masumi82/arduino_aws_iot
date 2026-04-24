import asyncio
import json
import logging

import serial

logger = logging.getLogger(__name__)


class UartWriter:
    def __init__(self, serial_port: serial.Serial) -> None:
        self._serial = serial_port

    async def write(self, payload: dict) -> None:
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._serial.write, data)
        logger.info(json.dumps({"event": "uart_cmd_sent", "type": payload.get("type"),
                                "commandId": payload.get("commandId")}))
