import asyncio
import json
import logging
import signal
import time

import serial

from command_handler import CommandHandler
from config import load_config
from mqtt_client import MqttClient
from status_monitor import StatusMonitor
from uart_reader import UartReader
from uart_writer import UartWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # messages are already JSON
)
logger = logging.getLogger(__name__)


async def _telemetry_loop(
    queue: asyncio.Queue,
    device_id: str,
    mqtt_client: MqttClient,
    status_monitor: StatusMonitor,
) -> None:
    while True:
        frame = await queue.get()
        frame["timestamp"] = int(time.time() * 1000)  # overwrite with RPi UTC
        status_monitor.on_telemetry_received()         # timer reset + online publish
        topic = f"device/{device_id}/telemetry"
        await mqtt_client.publish(topic, frame, retain=True)
        logger.info(json.dumps({"event": "telemetry_published",
                                "sequenceNo": frame.get("sequenceNo"),
                                "deviceId": device_id}))


async def _shutdown(
    tasks: list[asyncio.Task],
    mqtt_client: MqttClient,
) -> None:
    logger.info(json.dumps({"event": "shutdown_started"}))
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await mqtt_client.disconnect()
    logger.info(json.dumps({"event": "shutdown_completed"}))


async def main() -> None:
    config = load_config()
    logger.info(json.dumps({"event": "gateway_starting",
                            "deviceId": config.device_id}))

    telemetry_queue: asyncio.Queue = asyncio.Queue()
    serial_port = serial.Serial()

    uart_writer  = UartWriter(serial_port)
    uart_reader  = UartReader(config, telemetry_queue, serial_port)
    mqtt_client  = MqttClient(config)
    cmd_handler  = CommandHandler(config, uart_writer)
    status_mon   = StatusMonitor(config, mqtt_client.publish)

    mqtt_client.set_command_callback(cmd_handler.handle)
    mqtt_client.add_reconnect_callback(status_mon.reset_state)
    await mqtt_client.connect()

    tasks: list[asyncio.Task] = [
        asyncio.create_task(uart_reader.run(), name="uart_reader"),
        asyncio.create_task(status_mon.run(), name="status_monitor"),
        asyncio.create_task(
            _telemetry_loop(telemetry_queue, config.device_id, mqtt_client, status_mon),
            name="telemetry_loop",
        ),
    ]

    loop = asyncio.get_running_loop()
    shutdown_task: asyncio.Task | None = None

    def _handle_signal():
        nonlocal shutdown_task
        if shutdown_task is None:
            shutdown_task = asyncio.create_task(_shutdown(tasks, mqtt_client))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
