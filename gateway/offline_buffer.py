import json
import logging
import time
from collections import deque
from typing import Awaitable, Callable

from config import Config

logger = logging.getLogger(__name__)


class OfflineBuffer:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._buffer: deque[tuple[str, dict, float]] = deque()  # (topic, payload, pushed_at)
        logger.info(json.dumps({"event": "buffer_initialized", "note": "in-memory only"}))

    def push(self, topic: str, payload: dict) -> None:
        if len(self._buffer) >= self._config.buffer_max_size:
            self._buffer.popleft()
            logger.warning(json.dumps({"event": "offline_buffer_drop",
                                       "reason": "size_limit",
                                       "max_size": self._config.buffer_max_size}))
        self._buffer.append((topic, payload, time.monotonic()))

    async def flush(self, publish_fn: Callable[[str, dict], Awaitable[None]]) -> None:
        now = time.monotonic()
        flushed = expired = 0
        while self._buffer:
            topic, payload, pushed_at = self._buffer[0]  # peek before consuming
            if now - pushed_at > self._config.buffer_max_age_sec:
                self._buffer.popleft()
                expired += 1
                logger.info(json.dumps({"event": "offline_buffer_expire", "topic": topic}))
                continue
            await publish_fn(topic, payload)  # remove only after successful publish
            self._buffer.popleft()
            flushed += 1
        if flushed or expired:
            logger.info(json.dumps({"event": "buffer_flushed",
                                    "flushed": flushed, "expired": expired}))
