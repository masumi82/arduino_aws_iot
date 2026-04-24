# 詳細設計書

| 項目 | 内容 |
|------|------|
| プロジェクト名 | arduino_aws_iot |
| バージョン | 1.1.0 |
| 作成日 | 2026-04-24 |
| 最終更新 | 2026-04-24（Codex レビュー反映） |
| 前提文書 | docs/02_basic_design/basic_design.md v1.1.0 |
| ステータス | Draft |

---

## 1. はじめに

### 1.1 目的

本書は基本設計書に基づき、各コンポーネントの実装に必要な詳細仕様を定義する。実装担当者が本書と基本設計書を参照することで、設計判断が不要な状態でコーディングを開始できることを目標とする。

### 1.2 対象コンポーネント

| コンポーネント | 設計範囲 |
|---|---|
| Arduino ファームウェア | 処理フロー・データ構造・EEPROM マップ |
| Gateway (uart_bridge) | クラス設計・メソッドシグネチャ・バリデーション仕様・起動/停止シーケンス |
| Web ダッシュボード | ファイル構成・JS モジュール設計 |
| Terraform | ファイル構成・変数/出力値定義 |
| テスト | テスト計画（単体・結合・E2E） |

---

## 2. トレーサビリティ

| 要件 ID | 要件概要 | 基本設計節 | 詳細設計節 |
|--------|---------|-----------|-----------|
| REQ-F-01 | 疑似センサーデータ生成（温湿度ランダムウォーク） | §4.1 | §3.2 |
| REQ-F-02 | UART による Arduino↔Gateway 通信 | §3.1 | §3.3, §4.3 |
| REQ-F-03 | MQTT/TLS による Gateway→AWS IoT Core 接続 | §3.2 | §4.4, §4.6 |
| REQ-F-04 | センサーデータのリアルタイム Web 表示 | §6 | §6.1 |
| REQ-F-05 | Web からの制御コマンド送受信 | §2.2, §6 | §4.5, §6.2 |
| REQ-F-06 | LED 制御・送信間隔変更コマンド対応 | §3.1, §3.2 | §3.4, §4.5 |
| REQ-F-07 | setInterval 値の EEPROM 永続化 | §4.2 | §3.3 |
| REQ-F-08 | 接続状態の Web 表示（online/degraded/offline） | §3.3 | §4.7, §6.3 |
| REQ-F-09 | MQTT 切断中のオフラインバッファ | §5.2 | §4.8 |
| REQ-NF-01 | AWS 無料枠内運用（送信間隔 5〜30 秒） | §1 | §3.2 |
| REQ-NF-02 | LAN 内のみ HTTP 許容・外部公開時 TLS 必須 | §8 | §7 |

---

## 3. Arduino ファームウェア詳細設計

### 3.1 ソフトウェア構成

```
firmware/arduino_mkr_zero/
├── arduino_mkr_zero.ino   ← メインスケッチ（setup/loop）
├── sensor.h / sensor.cpp  ← 疑似センサーロジック
├── uart_comm.h / .cpp     ← UART 送受信
└── config.h               ← 定数定義
```

### 3.2 疑似センサー詳細（sensor.cpp）

**アルゴリズム（ランダムウォーク）:**

```
delta = random(-DELTA_MAX, +DELTA_MAX)  // 整数乱数を 0.1 スケール
next  = current + delta
next  = clamp(next, MIN, MAX)           // 境界丸め
```

**パラメータ定数（config.h）:**

```cpp
// 温度
const float TEMP_INIT    = 25.0f;
const float TEMP_MIN     = 15.0f;
const float TEMP_MAX     = 35.0f;
const float TEMP_DELTA   = 0.5f;   // 1回の最大変動幅

// 湿度
const float HUMID_INIT   = 50.0f;
const float HUMID_MIN    = 20.0f;
const float HUMID_MAX    = 80.0f;
const float HUMID_DELTA  = 1.0f;

// 送信間隔
const uint32_t INTERVAL_DEFAULT_MS = 10000;
const uint32_t INTERVAL_MIN_MS     =  5000;
const uint32_t INTERVAL_MAX_MS     = 30000;
```

### 3.3 データ構造

**Telemetry フレーム（UART 送信）:**

```cpp
struct TelemetryFrame {
    const char* schemaVersion;  // "1.0"
    const char* deviceId;       // "arduino-mkr-001"
    uint64_t    timestamp;      // Unix ミリ秒（UART 受信側で RTC 不要→0 固定可）
    float       temperatureC;
    float       humidityPct;
    bool        ledState;
    uint32_t    intervalMs;
    uint32_t    sequenceNo;     // 単調増加、起動時 0
};
```

> **timestamp について:** Arduino MKR Zero は RTC 未搭載。timestamp は 0 固定で送出し、Raspberry Pi Gateway が受信時刻（UTC エポックミリ秒）で上書きして publish する。

**EEPROM アドレスマップ:**

| アドレス | バイト数 | 型 | 内容 |
|---------|---------|---|------|
| 0x00 | 4 | uint32_t | intervalMs |
| 0x04 | 1 | uint8_t | マジックバイト（0xAB で書き込み済みを識別） |

- マジックバイト != 0xAB → 未初期化とみなし INTERVAL_DEFAULT_MS を使用
- intervalMs が [INTERVAL_MIN_MS, INTERVAL_MAX_MS] 範囲外 → INTERVAL_DEFAULT_MS にフォールバック

**Command フレーム（UART 受信）:**

```cpp
struct CommandFrame {
    char     commandId[37];  // UUID v4 文字列（36字 + null終端）
    char     type[16];       // "setLed" or "setInterval"
    JsonVariant value;       // bool or int（ArduinoJson で受け取る）
};
```

### 3.4 処理フロー

図: `diagrams/activity_arduino.puml`

**setup():**
1. UART 初期化（115,200 bps）
2. EEPROM から intervalMs 読み出し（マジックバイト確認）
3. LED ピン出力設定、初期状態 OFF
4. 疑似センサー初期化（初期値セット）
5. sequenceNo = 0

**loop():**
1. 送信タイマー確認（millis() - lastSendAt >= intervalMs）
   - 経過時: センサー値更新 → JSON シリアライズ → UART 送信 → sequenceNo++
2. UART 読み取り確認（Serial.available()）
   - 受信バイトあり: JSON パース → コマンド実行
3. LED 状態は ledState フラグで管理（コマンド受信時に書き込み）

**コマンド実行:**

| type | value 型 | 処理 |
|------|----------|------|
| `setLed` | bool（true/false 厳密） | ledState 更新、digitalWrite |
| `setInterval` | int [5000, 30000] | intervalMs 更新、現在値と異なる場合のみ EEPROM 書き込み |
| その他 / 型不一致 | — | 無視（UART にエラーを返さない） |

---

## 4. Gateway 詳細設計

### 4.1 ライブラリ選定

| 用途 | ライブラリ | バージョン |
|------|-----------|---------|
| MQTT | `awsiotsdk` (aws-iot-device-sdk-python-v2) | 最新安定版 |
| UART | `pyserial` | 3.5+ |
| 非同期 | Python 標準 `asyncio` | Python 3.11 |
| JSON | Python 標準 `json` | — |
| 環境変数 | Python 標準 `os` | — |

> **clean_session について:** aws-iot-device-sdk-v2 は MQTT 接続時に `clean_session=True` を強制する（ブローカー側で永続セッション非対応）。再接続後は subscription を明示的に復元する必要がある。`mqtt_client.py` の接続確立コールバック内で cmd トピックを再 subscribe する。

### 4.2 クラス設計

図: `diagrams/class_gateway.puml`

#### config.py

```python
@dataclass(frozen=True)
class Config:
    iot_endpoint: str        # AWS IoT Core エンドポイント
    device_id: str           # デバイス ID（デフォルト: "arduino-mkr-001"）
    cert_path: str           # X.509 証明書パス
    key_path: str            # 秘密鍵パス
    ca_path: str             # CA 証明書パス
    uart_port: str           # UART デバイスパス（デフォルト: "/dev/ttyACM0"）
    uart_baudrate: int       # ボーレート（デフォルト: 115200）
    status_degraded_sec: int # degraded タイマー秒数（デフォルト: 15）
    buffer_max_size: int     # オフラインバッファ上限件数（デフォルト: 50）
    buffer_max_age_sec: int  # オフラインバッファ最大保持秒数（デフォルト: 600）

def load_config() -> Config:
    """環境変数から Config を生成。必須項目が未設定なら ValueError を送出。"""
```

**環境変数一覧:**

| 環境変数名 | 型 | 必須 | デフォルト | 説明 |
|-----------|---|------|----------|------|
| `IOT_ENDPOINT` | str | ✅ | — | AWS IoT Core エンドポイント FQDN |
| `DEVICE_ID` | str | | `arduino-mkr-001` | IoT Thing 名 |
| `CERT_PATH` | str | ✅ | — | デバイス証明書 .pem パス |
| `KEY_PATH` | str | ✅ | — | 秘密鍵 .pem パス |
| `CA_PATH` | str | ✅ | — | AWS ルート CA .pem パス |
| `UART_PORT` | str | | `/dev/ttyACM0` | UART デバイスパス |
| `UART_BAUDRATE` | int | | `115200` | UART ボーレート |
| `STATUS_DEGRADED_SEC` | int | | `15` | degraded 判定秒数 |
| `BUFFER_MAX_SIZE` | int | | `50` | オフラインバッファ上限件数 |
| `BUFFER_MAX_AGE_SEC` | int | | `600` | バッファ保持最大秒数 |

#### uart_reader.py

```python
class UartReader:
    def __init__(self, config: Config, telemetry_queue: asyncio.Queue): ...

    async def run(self) -> None:
        """UART を継続読み取り。切断時は 5 秒待機後に再接続。"""

    def _parse_frame(self, raw: bytes) -> dict | None:
        """JSON パース。失敗時は None を返しエラーログを出力。512 バイト超過時も None。"""
```

#### mqtt_client.py

```python
class MqttClient:
    def __init__(self, config: Config): ...

    async def connect(self) -> None:
        """MQTT 接続・LWT 登録。接続確立コールバックで cmd を subscribe。"""

    async def publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        """JSON シリアライズして publish。切断中は offline_buffer に委譲。"""

    async def disconnect(self) -> None:
        """
        正常停止時: status:offline を明示 publish してから MQTT 切断。
        異常切断時（ネットワーク障害等）: AWS IoT Core が LWT を発動して
        offline を自動送信するため、本メソッドは呼ばれない。
        """

    def set_command_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        """cmd トピック受信時のコールバックを登録。"""

    async def _reconnect_loop(self) -> None:
        """指数バックオフ（1→2→4→…→60 秒）で再接続を試みる。"""
```

#### command_handler.py

```python
class CommandHandler:
    def __init__(self, config: Config, uart_writer: UartWriter): ...

    async def handle(self, payload: dict) -> None:
        """コマンドバリデーション → commandId 重複チェック → UART 転送。"""

    def _validate(self, payload: dict) -> bool:
        """バリデーション仕様に従い True/False を返す。"""

    def _is_duplicate(self, command_id: str) -> bool:
        """commandId キャッシュを確認。重複なら True。"""
```

#### status_monitor.py

```python
class StatusMonitor:
    def __init__(self, config: Config, mqtt_client: MqttClient): ...

    def on_telemetry_received(self) -> None:
        """Telemetry 受信時に呼び出す。タイマーリセット + online publish。"""

    async def run(self) -> None:
        """1 秒ごとにタイマーを確認。15 秒超過で degraded publish。"""
```

#### offline_buffer.py

```python
class OfflineBuffer:
    def __init__(self, config: Config): ...

    def push(self, topic: str, payload: dict) -> None:
        """バッファに追加。上限超過時は最古エントリを破棄しワーニングログ。"""

    def flush(self, publish_fn: Callable) -> None:
        """バッファを時系列順に publish。期限切れエントリは破棄。"""
```

#### uart_writer.py（基本設計に implicit、詳細設計で追加）

```python
class UartWriter:
    def __init__(self, serial_port): ...

    async def write(self, payload: dict) -> None:
        """JSON シリアライズ + 改行付きで UART に書き込む。"""
```

#### main.py

```python
async def main() -> None:
    config = load_config()
    telemetry_queue: asyncio.Queue = asyncio.Queue()

    # 単一の serial.Serial を生成し、Reader と Writer に共有注入する
    # open は UartReader.run() 内部で行い、切断時の再接続も UartReader が管理する
    serial_port = serial.Serial()  # まだ open しない
    uart_writer = UartWriter(serial_port)
    uart_reader = UartReader(config, telemetry_queue, serial_port)

    mqtt_client = MqttClient(config)
    command_handler = CommandHandler(config, uart_writer)
    status_monitor = StatusMonitor(config, mqtt_client)

    # MQTT コマンド受信時のコールバックを登録
    mqtt_client.set_command_callback(command_handler.handle)

    await mqtt_client.connect()

    loop = asyncio.get_event_loop()
    tasks: list[asyncio.Task] = [
        asyncio.create_task(uart_reader.run()),
        asyncio.create_task(status_monitor.run()),
        asyncio.create_task(_telemetry_loop(telemetry_queue, mqtt_client, status_monitor)),
    ]

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(tasks, mqtt_client, uart_writer))
        )

    await asyncio.gather(*tasks, return_exceptions=True)


async def _telemetry_loop(
    queue: asyncio.Queue,
    mqtt_client: MqttClient,
    status_monitor: StatusMonitor,
) -> None:
    """Telemetry キューからフレームを取得し publish する。"""
    while True:
        frame = await queue.get()
        frame["timestamp"] = int(time.time() * 1000)  # RPi UTC 時刻で上書き
        status_monitor.on_telemetry_received()         # タイマーリセット + online publish
        await mqtt_client.publish(
            f"device/{frame['deviceId']}/telemetry", frame, retain=True
        )


async def shutdown(
    tasks: list[asyncio.Task],
    mqtt_client: MqttClient,
    uart_writer: UartWriter,
) -> None:
    """
    Graceful shutdown 順序:
      1. UartReader を停止（新規受信停止）
      2. telemetry_queue が空になるまで待機（最大 5 秒）
      3. StatusMonitor を停止
      4. MqttClient.disconnect()（status:offline publish → MQTT 切断）
      5. 残タスクをキャンセル
    """
```

> SIGTERM / SIGINT は `loop.add_signal_handler` で捕捉し `shutdown()` を呼び出す。

### 4.3 コマンドバリデーション仕様

`command_handler.py` の `_validate()` は以下をすべて満たす場合のみ `True` を返す。

| 項目 | 条件 |
|------|------|
| `commandId` 存在 | キーが存在し、値が文字列 |
| `commandId` 形式 | UUID v4 regex: `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` |
| `type` 存在 | キーが存在し値が文字列 |
| `type` 値 | `"setLed"` または `"setInterval"` のいずれか |
| `setLed` の `value` | `isinstance(value, bool)` が True（Python の bool 型厳密チェック） |
| `setInterval` の `value` | `isinstance(value, int)` かつ `5000 <= value <= 30000` |

バリデーション失敗時: `{event: "cmd_validation_error", reason: "...", commandId: "...", type: "..."}` をワーニングログ出力。UART 転送は行わない。

### 4.4 commandId キャッシュ仕様

- **データ構造:** `dict[str, float]` (`commandId` → 受信 UNIX タイム秒)
- **TTL:** 60 秒
- **Eviction:** `_is_duplicate()` 呼び出し時に lazy に期限切れエントリを掃除する
- **上限:** 上限なし（60 秒 TTL かつ最大 1 件/秒 → 最大約 60 エントリで安定）

```python
def _is_duplicate(self, command_id: str) -> bool:
    now = time.monotonic()
    # 期限切れを掃除
    self._cache = {k: v for k, v in self._cache.items() if now - v < 60}
    if command_id in self._cache:
        return True
    self._cache[command_id] = now
    return False
```

### 4.5 Telemetry パイプライン（非同期処理）

```
UartReader          asyncio.Queue          _telemetry_loop
    |                     |                      |
    |-- put(frame) ------>|                      |
    |                     |<-- get() ------------|
    |                     |    (1) timestamp 上書き（RPi UTC 時刻）
    |                     |    (2) StatusMonitor.on_telemetry_received()
    |                     |         └─ タイマーリセット + status:online publish
    |                     |    (3) MqttClient.publish(telemetry)
```

> `status:online` の publish は **StatusMonitor** が一元担当する（#4 対応）。

### 4.6 MQTT 接続シーケンス詳細

図: `diagrams/seq_startup.puml`

| ステップ | 処理 |
|---------|------|
| 1 | config.py: 環境変数バリデーション |
| 2 | mqtt_client: MQTT ブローカーへ TLS 接続（X.509 相互認証） |
| 3 | mqtt_client: LWT を `status/offline` で登録 |
| 4 | mqtt_client: `device/<id>/cmd` を subscribe |
| 5 | uart_reader: UART デバイスをオープン |
| 6 | status_monitor: 監視ループ開始 |
| 7 | main: Telemetry 処理ループ開始 |

### 4.7 状態遷移（Gateway Status）

図: `diagrams/state_gateway_status.puml`

| 状態 | publish 内容 | 遷移トリガー | publish 主体 |
|------|------------|------------|------------|
| online | `{"state":"online"}` | Telemetry 受信 | Gateway (StatusMonitor) |
| degraded | `{"state":"degraded"}` | 最後の Telemetry 受信から 15 秒超過 | Gateway (StatusMonitor) |
| offline | `{"state":"offline"}` | 異常切断: MQTT 接続断（LWT 発動） | AWS IoT Core (LWT) |
| offline | `{"state":"offline"}` | 正常停止: コンテナ停止・SIGTERM 受信 | Gateway (`disconnect()` 内で明示 publish) |

### 4.8 オフラインバッファ詳細

- **push タイミング:** `MqttClient.publish()` 呼び出し時に MQTT が未接続の場合
- **flush タイミング:** MQTT 再接続確立後、cmd subscribe 完了後に呼び出す
- **期限切れ判定:** push 時刻から `BUFFER_MAX_AGE_SEC` 秒（600 秒）を超えたエントリは flush 時に破棄
- **バッファ消失の通知:** コンテナ起動ログに `{event: "buffer_initialized", note: "in-memory only"}` を出力

---

## 5. Docker Compose / デプロイ詳細設計

### 5.1 ファイル構成

```
deploy/
├── docker-compose.yml
├── gateway/
│   └── Dockerfile
└── scripts/
    ├── build.sh          ← 開発機でのクロスビルドスクリプト
    └── deploy.sh         ← RPi へのデプロイスクリプト
```

### 5.2 ARM クロスビルド方法

**採用方法: `docker buildx` + QEMU（開発機上で ARM イメージをビルド）**

```bash
# 開発機（x86_64 Linux / macOS）
docker buildx create --use
docker buildx build \
  --platform linux/arm/v7 \
  -t arduino-gateway:latest \
  --output type=docker \
  ./deploy/gateway

docker save arduino-gateway:latest | gzip > gateway.tar.gz
scp gateway.tar.gz pi@raspberrypi:~/
ssh pi@raspberrypi 'docker load < gateway.tar.gz && docker compose -f ~/deploy/docker-compose.yml up -d'
```

> RPi 3B/4 は ARMv7（arm/v7）。RPi 5 を使う場合は `linux/arm64` に変更する。

### 5.3 docker-compose.yml 詳細

```yaml
version: "3.9"
services:
  gateway:
    image: arduino-gateway:latest
    restart: unless-stopped
    devices:
      - /dev/ttyACM0:/dev/ttyACM0    # Arduino USB-UART
    volumes:
      - /etc/arduino_iot/certs:/app/certs:ro
    env_file:
      - .env
    logging:
      driver: journald
      options:
        tag: arduino-gateway

  web:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - ../web:/usr/share/nginx/html:ro
    logging:
      driver: journald
      options:
        tag: arduino-web
```

---

## 6. Web ダッシュボード詳細設計

### 6.1 ファイル構成

```
web/
├── index.html
├── css/
│   └── style.css
└── js/
    ├── config.js          ← Cognito Pool ID / IoT エンドポイント（ビルド時に注入）
    ├── mqtt_client.js     ← MQTT over WebSocket 接続管理（MQTT.js）
    ├── telemetry.js       ← Telemetry 受信・sequenceNo 重複排除・Chart.js 更新
    ├── status.js          ← 接続状態表示（online/degraded/offline）
    └── command.js         ← コマンド送信・タイムアウト管理
```

### 6.2 JS モジュール設計

**config.js（ビルド時に Terraform output から生成）:**
```javascript
const CONFIG = {
  iotEndpoint: "xxxx.iot.ap-northeast-1.amazonaws.com",
  cognitoPoolId: "ap-northeast-1:xxxx-xxxx-xxxx",
  region: "ap-northeast-1",
  deviceId: "arduino-mkr-001"
};
```

**mqtt_client.js:**
- `connect()`: Cognito Identity Credentials 取得 → SigV4 署名 → WebSocket 接続
- 再接続: MQTT.js の自動再接続を使用（reconnectPeriod: 5000 ms）
- 接続成功時: `telemetry`, `status` トピックを subscribe

**telemetry.js:**
- `lastSeqNo = -1` で重複排除（`sequenceNo <= lastSeqNo` ならスキップ）
- Chart.js のローリングウィンドウ: 最新 30 件を保持
- 更新対象 UI: 温度/湿度の数値表示・グラフ・ledState・intervalMs・**最終受信時刻**
- 最終受信時刻の表示仕様:
  - Telemetry の `timestamp`（RPi UTC エポックミリ秒）をブラウザのローカル時刻に変換して表示
  - フォーマット: `new Date(frame.timestamp).toLocaleString()`（ブラウザのロケール設定に依存）
  - 更新対象 DOM: `<span id="last-received-at">` に書き込む
  - 初回ロード時（受信前）: `--` と表示

**status.js:**
- status トピック受信時に `<div id="status-badge">` のクラスを切り替え
- `online` → 緑、`degraded` → 黄、`offline` → 赤
- 初回ロード時は `pending`（灰色）で表示

**command.js:**

```javascript
const CMD_STATES = { IDLE: 'idle', SENDING: 'sending', WAITING: 'waiting' };

async function sendCommand(type, value) {
  const commandId = crypto.randomUUID();
  // state: SENDING
  await mqttClient.publish(`device/${CONFIG.deviceId}/cmd`, { commandId, type, value });
  // state: WAITING — 10秒タイマー起動
  // タイマー内に Telemetry で変化確認 → SUCCESS → IDLE
  // 10秒超過 → WARNING → IDLE
}
```

### 6.3 コマンド送信 UI 仕様

**表示項目:**

| UI 要素 | 内容 | 初期表示 |
|--------|------|---------|
| 温度表示 (`#temp-value`) | `temperatureC` [℃] | `--` |
| 湿度表示 (`#humid-value`) | `humidityPct` [%] | `--` |
| 温湿度グラフ | 直近 30 件のローリングウィンドウ | 空グラフ |
| LED 状態 (`#led-state`) | `ledState`（ON/OFF） | `--` |
| 送信間隔 (`#interval-value`) | `intervalMs` [ms] | `--` |
| 最終受信時刻 (`#last-received-at`) | `timestamp` のローカル時刻 | `--` |

**コマンド送信 UI:**

| UI 要素 | 操作 | 送信コマンド |
|--------|------|------------|
| LED ON ボタン | クリック | `{type:"setLed", value:true}` |
| LED OFF ボタン | クリック | `{type:"setLed", value:false}` |
| 送信間隔スライダー | 値変更後「適用」ボタン | `{type:"setInterval", value:<ms>}` |
| 送信中インジケータ | コマンド送信中に表示 | — |
| 未到達警告 | 10 秒タイムアウト時に表示 | — |

---

## 7. Terraform 詳細設計

### 7.1 ファイル構成

```
terraform/
├── main.tf              ← provider / backend 設定
├── variables.tf         ← 入力変数定義
├── outputs.tf           ← 出力値定義（config.js 生成に使用）
├── iot.tf               ← IoT Thing / Certificate / Policy
├── cognito.tf           ← Cognito Identity Pool / IAM Role
├── certs/               ← terraform apply で出力（.gitignore 対象）
│   ├── certificate.pem
│   ├── private.key
│   └── root_ca.pem
└── README.md
```

### 7.2 変数定義（variables.tf）

| 変数名 | 型 | デフォルト | 説明 |
|-------|---|----------|------|
| `aws_region` | string | `"ap-northeast-1"` | デプロイリージョン |
| `device_id` | string | `"arduino-mkr-001"` | IoT Thing 名・トピックプレフィックス |
| `project_name` | string | `"arduino-aws-iot"` | リソースタグ用プロジェクト名 |

### 7.3 出力値定義（outputs.tf）

| 出力名 | 内容 | 用途 |
|-------|------|------|
| `iot_endpoint` | AWS IoT Core エンドポイント FQDN | Gateway の環境変数・config.js |
| `cognito_identity_pool_id` | Cognito Identity Pool ID | config.js |
| `certificate_pem` | デバイス証明書（sensitive） | `certs/certificate.pem` に保存 |
| `private_key` | 秘密鍵（sensitive） | `certs/private.key` に保存 |

**証明書ファイルの自動出力（iot.tf に追記）:**

```hcl
# デバイス証明書をローカルファイルに出力
resource "local_file" "certificate_pem" {
  content         = aws_iot_certificate.device.certificate_pem
  filename        = "${path.module}/certs/certificate.pem"
  file_permission = "0600"
}

resource "local_file" "private_key" {
  content         = aws_iot_certificate.device.private_key
  filename        = "${path.module}/certs/private.key"
  file_permission = "0600"
}
```

**Root CA 証明書 (`root_ca.pem`) の取得:**

Root CA は Terraform で管理しない。`terraform apply` 後に手動でダウンロードする:

```bash
curl -o terraform/certs/root_ca.pem \
  https://www.amazontrust.com/repository/AmazonRootCA1.pem
chmod 600 terraform/certs/root_ca.pem
```

> AWS IoT Core は Amazon Root CA 1 (RSA 2048) を使用する。証明書が変わらない限り再ダウンロード不要。

### 7.4 IoT リソース詳細（iot.tf）

**aws_iot_thing:**
```hcl
resource "aws_iot_thing" "device" {
  name = var.device_id
}
```

**aws_iot_certificate:**
```hcl
resource "aws_iot_certificate" "device" {
  active = true
}
```

**aws_iot_policy:**
```hcl
resource "aws_iot_policy" "device" {
  name   = "${var.device_id}-policy"
  policy = data.aws_iam_policy_document.iot_device.json
}
```

**ポリシー要約（IAM Policy Document）:**
- `iot:Connect` → `client/${var.device_id}`
- `iot:Publish` → `topic/device/${var.device_id}/telemetry`, `topic/device/${var.device_id}/status`
- `iot:Subscribe`, `iot:Receive` → `topicfilter/device/${var.device_id}/cmd`, `topic/device/${var.device_id}/cmd`

**Certificate + Thing + Policy をアタッチ:**
```hcl
resource "aws_iot_thing_principal_attachment" "device" { ... }
resource "aws_iot_policy_attachment" "device" { ... }
```

### 7.5 Cognito リソース詳細（cognito.tf）

**aws_cognito_identity_pool:**
```hcl
resource "aws_cognito_identity_pool" "web" {
  identity_pool_name               = "arduino_iot_web_pool"
  allow_unauthenticated_identities = true
}
```

**aws_iam_role（未認証ロール）:**
```hcl
resource "aws_iam_role" "cognito_unauth" {
  name               = "arduino_iot_cognito_unauth"
  assume_role_policy = data.aws_iam_policy_document.cognito_assume.json
}
```

**IAM ポリシー（未認証ロール）:**
- `iot:Connect` → `client/web-*`
- `iot:Subscribe`, `iot:Receive` → `telemetry`, `status` トピック
- `iot:Publish` → `cmd` トピック

---

## 8. シーケンス図インデックス

| ファイル | 内容 |
|---------|------|
| `diagrams/seq_startup.puml` | システム起動・MQTT 接続・LWT 登録 |
| `diagrams/seq_telemetry.puml` | 正常系: Telemetry 受信・publish フロー |
| `diagrams/seq_command.puml` | 正常系: Web コマンド → Arduino 制御フロー |
| `diagrams/seq_error_uart.puml` | 異常系: UART 切断・再接続・degraded 遷移 |
| `diagrams/seq_error_mqtt.puml` | 異常系: MQTT 切断・バッファ・再接続・flush |
| `diagrams/class_gateway.puml` | Gateway モジュールクラス図 |
| `diagrams/state_gateway_status.puml` | Gateway ステータス状態機械 |
| `diagrams/activity_arduino.puml` | Arduino setup/loop フローチャート |

---

## 9. テスト計画

### 9.1 方針

| テスト層 | 環境 | ツール | 目的 |
|---------|------|-------|------|
| 単体テスト | 開発機 | pytest + unittest.mock | モジュール単独の正常/異常動作確認 |
| 結合テスト | 開発機 | pytest + Mosquitto (ローカル) | Gateway ↔ MQTT ブローカー間の動作確認 |
| E2E テスト | RPi + AWS | 手動チェックリスト | 実機を用いたフルフロー検証 |

### 9.2 単体テスト一覧

**uart_reader.py:**

| テストケース | 確認内容 |
|---|---|
| 正常 JSON フレームのパース | dict として返ること |
| 不正 JSON フレーム | None を返し `uart_parse_error` ログが出ること |
| 512 バイト超過フレーム | None を返し `uart_parse_error` ログが出ること |

**command_handler.py:**

| テストケース | 確認内容 |
|---|---|
| 正常な setLed コマンド | UART 転送メソッドが呼ばれること |
| 正常な setInterval コマンド | UART 転送メソッドが呼ばれること |
| commandId 重複 | UART 転送が呼ばれないこと |
| value 型不一致（setLed に数値） | ワーニングログ出力・UART 転送なし |
| value 範囲外（setInterval: 4000） | ワーニングログ出力・UART 転送なし |
| 未知の type | ワーニングログ出力・UART 転送なし |
| UUID v4 形式不正 | バリデーション失敗 |

**offline_buffer.py:**

| テストケース | 確認内容 |
|---|---|
| push → flush でデータが正しく publish される | publish が時系列順に呼ばれること |
| 上限超過時に最古エントリが破棄される | `offline_buffer_drop` ログが出ること |
| 期限切れエントリが flush 時に破棄される | 期限切れ分は publish されないこと |

**status_monitor.py:**

| テストケース | 確認内容 |
|---|---|
| 15 秒経過で degraded publish | publish が `{"state":"degraded"}` で呼ばれること |
| Telemetry 受信でタイマーリセット | 15 秒後に degraded にならないこと |

**config.py:**

| テストケース | 確認内容 |
|---|---|
| 必須環境変数欠如 | ValueError が送出されること |
| 数値型環境変数の型変換 | int として取得できること |

### 9.3 結合テスト一覧

**方針:** aws-iot-device-sdk-v2 は TLS/X.509 が必須のため、ローカル Mosquitto への差し替えはライブラリレベルで困難。代わりに以下の2アプローチを採用する。

- **アプローチA（モック境界）:** `MqttClient` に `publish_fn` インターフェースを注入可能にする。テスト時は `asyncio.Queue` を渡してメッセージを検査する。
- **アプローチB（AWS 実環境）:** AWS IoT Core の MQTT テストクライアントを使い、実認証で接続して動作確認する（E2E に近い）。

本テスト計画ではアプローチAを採用し、AWS リソースなしで動作を確認する。

| テストケース | 確認内容 |
|---|---|
| Telemetry の end-to-end publish | UART mock → Queue → publish_fn が正しい topic/payload で呼ばれること |
| MQTT 切断中のバッファ → 再接続後 flush | `OfflineBuffer.flush()` が再接続後に呼ばれ、バッファ内容が publish されること |
| cmd callback → command_handler 呼び出し | MQTT callback を直接呼び出し → `handle()` が UART write を実行すること |
| 再接続後の subscription 復元 | `_on_connected()` が cmd を re-subscribe すること |

### 9.4 E2E テストチェックリスト（手動）

```
□ terraform apply で AWS リソースが作成されること
□ Root CA を手動ダウンロードし terraform/certs/ に配置できること
□ Gateway コンテナが起動し MQTT 接続ログが出ること
□ Arduino を接続すると Telemetry が AWS IoT Core MQTT テストクライアントで見えること
□ Web ブラウザを開くと status が "pending" (灰色) 表示から始まること
□ Gateway 起動後、ブラウザで status が "online" (緑) に変わること
□ Web ブラウザでグラフにデータが流れること
□ 温度・湿度の数値表示が更新されること
□ 最終受信時刻がローカル時刻フォーマットで表示されること
□ ページをリロードしても Retain メッセージで即座に最新値が表示されること  ← Retain 動作確認
□ LED ON ボタンを押すと Arduino の LED が点灯すること
□ LED OFF ボタンを押すと Arduino の LED が消灯すること
□ コマンド送信後 10 秒以内に Telemetry で変化が確認できること（送信中インジケータが消えること）
□ 送信間隔スライダーで変更すると Telemetry の intervalMs が変わること
□ Arduino を抜くと 15 秒後に status が "degraded" (黄) になること
□ Gateway コンテナを停止すると status が "offline" (赤) になること
□ Gateway 再起動後に MQTT 再接続・Telemetry 再開すること
□ ブラウザタブを複数開いても全タブで同時更新されること（MQTT ブロードキャスト確認）
□ terraform destroy で全リソースが削除されること
```

---

## 付録A: Codex レビュー対応記録（v1.1.0）

| 指摘 # | 対応 | 備考 |
|--------|------|------|
| #1 最終受信時刻の表示仕様未定義 | 対応: §6.2 telemetry.js・§6.3 表示項目に追記 | |
| #2 offline の publish 主体矛盾 | 対応: §4.2 disconnect() に正常/異常2パスを明記、§4.7 状態遷移テーブルを更新 | |
| #3 serial.Serial 共有方法未定義 | 対応: §4.2 main.py を具体化（Serial 生成・注入・callback 配線） | |
| #4 status:online publish 二重化 | 対応: §4.5 を修正（StatusMonitor に一元化）、seq_telemetry.puml を更新 | |
| #5 Terraform 証明書出力仕様不完全 | 対応: §7.3 に local_file リソース・Root CA 取得手順を追記 | |
| #6 結合テストとライブラリ不整合 | 対応: §9.3 を修正（publish_fn 注入アプローチAを採用） | |
| #7 Web 側テストカバレッジ不足 | 対応: §9.4 E2E チェックリストに sequenceNo・Retain・タイムアウト検証項目を追加 | |
| #8 起動シーケンス図の不完全さ | 対応: seq_startup.puml を更新（UartWriter・CommandHandler・callback 登録を追加） | |

---

## 付録B: 基本設計からの変更点

| 変更内容 | 理由 |
|---------|------|
| `uart_writer.py` モジュールを追加 | UART 書き込みを UartReader から分離して責務を明確化 |
| `timestamp` を Gateway で上書きする仕様を追記 | Arduino MKR Zero に RTC がないため Gateway の受信時刻を使用 |
| commandId キャッシュに lazy eviction を採用 | 定期タスク不要でシンプル |
| ARM クロスビルドに docker buildx を採用 | RPi 上ビルドより再現性が高い |
