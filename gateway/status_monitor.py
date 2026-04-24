import asyncio
import json
import logging
import time

from config import Config

logger = logging.getLogger(__name__)


def _log_task(task: asyncio.Task) -> None:
    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(json.dumps({"event": "task_error", "error": str(exc)}))
    task.add_done_callback(_on_done)

_POLL_INTERVAL_SEC = 1.0


class StatusMonitor:
    def __init__(self, config: Config, publish_fn) -> None:
        self._config = config
        self._publish_fn = publish_fn
        self._last_received: float = time.monotonic()
        self._current_state: str = "offline"

    def on_telemetry_received(self) -> None:
        self._last_received = time.monotonic()
        _log_task(asyncio.ensure_future(self._publish_online()))

    def reset_state(self) -> None:
        """Call after MQTT reconnect so next telemetry re-publishes online."""
        self._current_state = "offline"

    async def _publish_online(self) -> None:
        if self._current_state == "online":
            return  # no state change, skip publish
        self._current_state = "online"
        topic = f"device/{self._config.device_id}/status"
        await self._publish_fn(topic, {"state": "online"}, retain=True)
        logger.info(json.dumps({"event": "status_online"}))

    async def run(self) -> None:
        while True:
            await asyncio.sleep(_POLL_INTERVAL_SEC)
            elapsed = time.monotonic() - self._last_received
            if (self._current_state == "online" and
                    elapsed >= self._config.status_degraded_sec):
                self._current_state = "degraded"
                topic = f"device/{self._config.device_id}/status"
                await self._publish_fn(topic, {"state": "degraded"}, retain=True)
                logger.info(json.dumps({"event": "status_degraded",
                                        "elapsed_sec": round(elapsed, 1)}))
