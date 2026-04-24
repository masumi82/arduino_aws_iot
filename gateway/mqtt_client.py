import asyncio
import json
import logging
from typing import Awaitable, Callable

from awscrt import mqtt
from awsiot import mqtt_connection_builder

from config import Config
from offline_buffer import OfflineBuffer

logger = logging.getLogger(__name__)

def _log_task(task: asyncio.Task) -> None:
    """Log unhandled exceptions from fire-and-forget tasks."""
    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(json.dumps({"event": "task_error", "error": str(exc)}))
    task.add_done_callback(_on_done)


class MqttClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._buffer = OfflineBuffer(config)
        self._connection = None
        self._connected = False
        self._command_callback: Callable[[dict], Awaitable[None]] | None = None
        self._reconnect_callbacks: list[Callable[[], None]] = []

    def set_command_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        self._command_callback = cb

    def add_reconnect_callback(self, cb: Callable[[], None]) -> None:
        self._reconnect_callbacks.append(cb)

    async def connect(self) -> None:
        lwtpayload = json.dumps({"state": "offline"})
        self._connection = mqtt_connection_builder.mtls_from_path(
            endpoint         = self._config.iot_endpoint,
            cert_filepath    = self._config.cert_path,
            pri_key_filepath = self._config.key_path,
            ca_filepath      = self._config.ca_path,
            client_id        = self._config.device_id,
            clean_session    = True,
            will             = mqtt.Will(
                topic   = f"device/{self._config.device_id}/status",
                payload = lwtpayload.encode(),
                qos     = mqtt.QoS.AT_LEAST_ONCE,
                retain  = True,
            ),
            on_connection_interrupted = self._on_disconnected,
            on_connection_resumed     = self._on_resumed,
        )
        connect_future, _ = self._connection.connect()
        await asyncio.wrap_future(connect_future)
        self._connected = True
        logger.info(json.dumps({"event": "mqtt_connected",
                                "deviceId": self._config.device_id}))
        await self._subscribe_cmd()

    async def disconnect(self) -> None:
        topic = f"device/{self._config.device_id}/status"
        await self._do_publish(topic, {"state": "offline"}, retain=True)
        if self._connection:
            disconnect_future, _ = self._connection.disconnect()
            await asyncio.wrap_future(disconnect_future)
        self._connected = False
        logger.info(json.dumps({"event": "mqtt_disconnected"}))

    async def publish(self, topic: str, payload: dict,
                      qos: int = 1, retain: bool = False) -> None:
        if not self._connected:
            self._buffer.push(topic, payload)
            return
        await self._do_publish(topic, payload, retain=retain)

    async def _do_publish(self, topic: str, payload: dict, retain: bool) -> None:
        assert self._connection is not None
        body = json.dumps(payload, separators=(",", ":"))
        pub_future, _ = self._connection.publish(
            topic   = topic,
            payload = body,
            qos     = mqtt.QoS.AT_LEAST_ONCE,
            retain  = retain,
        )
        await asyncio.wrap_future(pub_future)

    async def _subscribe_cmd(self) -> None:
        assert self._connection is not None
        cmd_topic = f"device/{self._config.device_id}/cmd"
        sub_future, _ = self._connection.subscribe(
            topic    = cmd_topic,
            qos      = mqtt.QoS.AT_LEAST_ONCE,
            callback = self._on_message,
        )
        await asyncio.wrap_future(sub_future)
        logger.info(json.dumps({"event": "mqtt_subscribed", "topic": cmd_topic}))

    def _on_message(self, topic: str, payload: bytes, **kwargs) -> None:  # noqa: ARG002
        if self._command_callback is None:
            return
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(json.dumps({"event": "mqtt_parse_error", "reason": str(exc)}))
            return
        _log_task(asyncio.ensure_future(self._command_callback(data)))

    def _on_disconnected(self, connection, error, **kwargs) -> None:  # noqa: ARG002
        self._connected = False
        logger.warning(json.dumps({"event": "mqtt_disconnected", "reason": str(error)}))
        # SDK handles automatic reconnection; _on_resumed fires when reconnected.

    def _on_resumed(self, connection, return_code, session_present, **kwargs) -> None:  # noqa: ARG002
        self._connected = True
        logger.info(json.dumps({"event": "mqtt_reconnected"}))
        # clean_session=True means subscriptions are lost on reconnect, must re-subscribe.
        _log_task(asyncio.ensure_future(self._on_reconnected()))

    async def _on_reconnected(self) -> None:
        for cb in self._reconnect_callbacks:
            cb()
        await self._subscribe_cmd()
        await self._buffer.flush(self._do_publish_wrapper)

    async def _do_publish_wrapper(self, topic: str, payload: dict) -> None:
        await self._do_publish(topic, payload, retain=False)
