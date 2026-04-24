import json
import logging
import re
import time

from config import Config
from uart_writer import UartWriter

logger = logging.getLogger(__name__)

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CACHE_TTL_SEC = 60


class CommandHandler:
    def __init__(self, config: Config, uart_writer: UartWriter) -> None:
        self._config = config
        self._uart_writer = uart_writer
        self._cache: dict[str, float] = {}

    async def handle(self, payload: dict) -> None:
        if not self._validate(payload):
            return
        command_id: str = payload["commandId"]
        if self._is_duplicate(command_id):
            logger.warning(json.dumps({"event": "cmd_duplicate",
                                       "commandId": command_id}))
            return
        await self._uart_writer.write(payload)
        logger.info(json.dumps({"event": "cmd_forwarded",
                                "commandId": command_id,
                                "type": payload.get("type")}))

    def _validate(self, payload: dict) -> bool:
        cid = payload.get("commandId")
        if not isinstance(cid, str) or not _UUID_V4_RE.match(cid):
            self._log_validation_error("invalid_commandId", payload)
            return False

        typ = payload.get("type")
        if typ not in ("setLed", "setInterval"):
            self._log_validation_error("unknown_type", payload)
            return False

        value = payload.get("value")
        if typ == "setLed":
            if not isinstance(value, bool):
                self._log_validation_error("setLed_value_not_bool", payload)
                return False
        else:  # setInterval
            if not isinstance(value, int) or isinstance(value, bool):
                self._log_validation_error("setInterval_value_not_int", payload)
                return False
            if not (5000 <= value <= 30000):
                self._log_validation_error("setInterval_out_of_range", payload)
                return False
        return True

    def _is_duplicate(self, command_id: str) -> bool:
        now = time.monotonic()
        self._cache = {k: v for k, v in self._cache.items() if now - v < _CACHE_TTL_SEC}
        if command_id in self._cache:
            return True
        self._cache[command_id] = now
        return False

    def _log_validation_error(self, reason: str, payload: dict) -> None:
        logger.warning(json.dumps({
            "event": "cmd_validation_error",
            "reason": reason,
            "commandId": payload.get("commandId"),
            "type": payload.get("type"),
        }))
