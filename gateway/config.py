import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    iot_endpoint: str
    device_id: str
    cert_path: str
    key_path: str
    ca_path: str
    uart_port: str
    uart_baudrate: int
    status_degraded_sec: int
    buffer_max_size: int
    buffer_max_age_sec: int


def load_config() -> Config:
    def _require(key: str) -> str:
        v = os.environ.get(key, "").strip()
        if not v:
            raise ValueError(f"Required environment variable not set: {key}")
        return v

    def _int(key: str, default: int) -> int:
        raw = os.environ.get(key, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"Environment variable {key} must be an integer, got: {raw!r}")

    return Config(
        iot_endpoint         = _require("IOT_ENDPOINT"),
        device_id            = os.environ.get("DEVICE_ID", "arduino-mkr-001").strip() or "arduino-mkr-001",
        cert_path            = _require("CERT_PATH"),
        key_path             = _require("KEY_PATH"),
        ca_path              = _require("CA_PATH"),
        uart_port            = os.environ.get("UART_PORT", "/dev/ttyACM0").strip() or "/dev/ttyACM0",
        uart_baudrate        = _int("UART_BAUDRATE", 115200),
        status_degraded_sec  = _int("STATUS_DEGRADED_SEC", 15),
        buffer_max_size      = _int("BUFFER_MAX_SIZE", 50),
        buffer_max_age_sec   = _int("BUFFER_MAX_AGE_SEC", 600),
    )
