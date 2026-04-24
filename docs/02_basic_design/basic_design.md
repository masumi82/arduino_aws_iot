# 基本設計書

| 項目 | 内容 |
|------|------|
| プロジェクト名 | arduino_aws_iot |
| バージョン | 1.1.0 |
| 作成日 | 2026-04-24 |
| 最終更新 | 2026-04-24（Codex レビュー反映） |
| 前提文書 | docs/01_requirements/requirements.md v1.1.0 |
| ステータス | Draft |

---

## 1. システムアーキテクチャ

### 1.1 概要

本システムは 4 層で構成される。

```
デバイス層   →  ゲートウェイ層  →  クラウド層  →  クライアント層
Arduino        Raspberry Pi       AWS IoT Core    Web ブラウザ
(MKR Zero)     (Docker Compose)   + Cognito
```

図: `diagrams/system_overview.puml`

### 1.2 コンポーネント一覧

| コンポーネント | 実行環境 | 技術 | 役割 |
|---|---|---|---|
| Arduino ファームウェア | Arduino MKR Zero (Flash) | C++ / Arduino Framework | 疑似センサーデータ生成・UART 送受信・LED 制御 |
| Gateway (uart_bridge) | RPi Docker コンテナ | Python 3.11 / asyncio | UART ↔ MQTT 変換・接続管理・状態監視・コマンド転送 |
| Web サーバー | RPi Docker コンテナ | nginx:alpine | 静的 Web ファイル配信（LAN 内 HTTP） |
| Web ダッシュボード | ブラウザ | Vanilla JS / MQTT.js / Chart.js | リアルタイム監視・遠隔制御 UI |
| AWS IoT Core | AWS マネージド | MQTT ブローカー | デバイス-クラウド間の MQTT 中継 |
| Cognito Identity Pool | AWS マネージド | Cognito | Web ブラウザへの一時 AWS 認証情報払い出し |
| Terraform | 開発者 PC | HCL | AWS リソースの IaC 管理 |

---

## 2. データフロー

図: `diagrams/data_flow.puml`

### 2.1 監視フロー（Telemetry + Status: デバイス → Web）

```
Arduino            RPi Gateway              AWS IoT Core        Web Browser
  |                    |                         |                    |
  |                    |-- MQTT Connect -------->|                    |
  |                    |   LWT: status/offline    |                    |
  |                    |                         |                    |
  |-- JSON (UART) ---->|                         |                    |
  |                    |-- Publish (telemetry) -->|                    |
  |                    |-- Publish (status:      |                    |
  |                    |   online) ------------->|                    |
  |                    |                         |-- MQTT (WSS) ----->|
  |                    |                         |   subscribe all    |
  |                    |                         |                    |-- UI 更新
  |                    |                         |                    |   (telemetry/status)
  :  15秒間 Telemetry なし  :                    |                    |
  |                    |-- Publish (status: ----->|                    |
  |                    |   degraded)             |                    |-- degraded 表示
  :  MQTT 断           :                         |                    |
  |                    |×× 切断 ×× LWT -------->|                    |
  |                    |                         |-- status:offline ->|-- offline 表示
```

### 2.2 制御フロー（Command: Web → Arduino）

```
Web Browser         AWS IoT Core         RPi Gateway          Arduino
  |                      |                    |                   |
  |-- Publish (cmd) ---->|                    |                   |
  |   commandId=UUID     |-- subscribe ------>|                   |
  |                      |                    |-- バリデーション   |
  |                      |                    |   OK?              |
  |                      |                    |-- JSON (UART) ---->|
  |                      |                    |                   |-- 実行
  |<--- 次の Telemetry (10秒以内) で結果反映 ----------------------|
  |                      |                    |                    |
  : 10 秒超過で Web が未到達警告表示 :        |                    |
  |                      |                    |                    |
  --- バリデーション NG の場合 ---             |                    |
  |                      |                    |-- ワーニングログ   |
  |                      |                    |   UART 転送しない  |
```

---

## 3. インターフェース設計

### 3.1 UART プロトコル（Arduino ↔ RPi Gateway）

| 項目 | 仕様 |
|------|------|
| ボーレート | 115,200 bps |
| データビット | 8 |
| パリティ | なし |
| ストップビット | 1 |
| フロー制御 | なし |
| フレーム形式 | JSON + 改行（`\n`）区切り |
| 文字コード | UTF-8 |
| 最大フレームサイズ | 512 バイト |

**フレーム破損時の回復方針:**
- パースエラー発生時は改行（`\n`）まで読み飛ばして再同期
- 512 バイト超過時はそのフレームを破棄し、次の改行から再開
- いずれもエラーログに `{event: "uart_parse_error", reason: "..."}` を出力

**Arduino → Gateway（Telemetry）:**
```json
{"schemaVersion":"1.0","deviceId":"arduino-mkr-001","timestamp":1714000000000,"temperatureC":23.4,"humidityPct":55.2,"ledState":false,"intervalMs":10000,"sequenceNo":42}
```

**Gateway → Arduino（Command）:**
```json
{"commandId":"550e8400-e29b-41d4-a716-446655440000","type":"setLed","value":true}
{"commandId":"550e8400-e29b-41d4-a716-446655440001","type":"setInterval","value":10000}
```

### 3.2 MQTT トピック設計

| トピック | QoS | Retain | Publisher | Subscriber | 内容 |
|---------|-----|--------|-----------|-----------|------|
| `device/arduino-mkr-001/telemetry` | 1 | **true** | Gateway | Web | センサーデータ（Retain=true で初回表示に最新値を提供） |
| `device/arduino-mkr-001/status` | 1 | true | Gateway（通常 + LWT） | Web | 接続状態（`online`/`degraded`/`offline`） |
| `device/arduino-mkr-001/cmd` | 1 | false | Web | Gateway | 制御コマンド |

**QoS 1 重複対策:**
- `telemetry`: Web 側は受信時に `sequenceNo` を確認し、前回以下の値なら表示をスキップ
- `cmd`: Gateway は直近 60 秒内に処理済みの `commandId` をメモリキャッシュし、重複受信時は UART 転送しない

### 3.3 status トピック publish 規則

| トリガー | publish する値 | publish 主体 |
|---------|--------------|-------------|
| Telemetry を UART 受信した直後 | `{"state":"online"}` | Gateway（通常 publish） |
| 最後の Telemetry 受信から 15 秒超過 | `{"state":"degraded"}` | Gateway（内部タイマー） |
| MQTT 接続確立時（LWT 登録） | 自動（接続断時に送信） | AWS IoT Core（LWT） |
| MQTT 切断発生 | `{"state":"offline"}` | AWS IoT Core（LWT 発動） |

---

## 4. Arduino 仕様

### 4.1 疑似センサー生成アルゴリズム

| パラメータ | 温度 | 湿度 |
|-----------|------|------|
| 初期値 | 25.0℃ | 50.0% |
| 範囲 | 15.0〜35.0℃ | 20.0〜80.0% |
| 1 回の変動幅 | ±0.5℃ 以内 | ±1.0% 以内 |
| 範囲超過時 | 境界値に丸める | 境界値に丸める |

### 4.2 起動時の状態初期化

```
電源投入
  └─ EEPROM から intervalMs を読み出し
       ├─ 5,000〜30,000 の範囲内 → その値を採用
       └─ 範囲外または未書き込み → デフォルト 10,000ms を採用
```

**EEPROM 書き込み条件:**
- setInterval コマンドを受信し、値が現在値と異なる場合のみ書き込む
- 同値の場合は書き込みスキップ（EEPROM 寿命保護）

---

## 5. Gateway 設計

### 5.1 モジュール構成

| モジュール | 責務 |
|-----------|------|
| `main.py` | 起動・シグナルハンドリング・全体オーケストレーション |
| `uart_reader.py` | UART 読み取り、改行区切り JSON パース、非同期 Queue へ投入 |
| `mqtt_client.py` | AWS IoT Core 接続、publish、subscribe、LWT 登録、再接続 |
| `command_handler.py` | MQTT コマンド受信・バリデーション・UART 転送・commandId キャッシュ |
| `status_monitor.py` | Telemetry 受信タイマー監視・status publish（online/degraded） |
| `offline_buffer.py` | MQTT 切断中の Telemetry バッファ管理・再送 |
| `config.py` | 環境変数バリデーション |

### 5.2 オフラインバッファ仕様

| 項目 | 仕様 |
|------|------|
| 保持件数上限 | 50 件 |
| 保持時間上限 | 10 分 |
| 上限超過時 | 古いデータから破棄、ワーニングログ出力 |
| 再送順序 | 時系列順（古い順）で publish |
| 再起動時 | バッファはメモリ保持のため消失する（学習用途として許容、README に明記） |

### 5.3 再接続戦略

| 障害 | 再接続戦略 |
|------|-----------|
| MQTT 切断 | 指数バックオフ（1→2→4→8→…→最大 60 秒） |
| UART 切断 | 固定 5 秒間隔 |

### 5.4 ログ仕様

出力形式: JSON Lines（stdout）

```json
{"timestamp":"2026-04-24T00:00:00Z","event":"mqtt_connected","deviceId":"arduino-mkr-001"}
{"timestamp":"2026-04-24T00:00:01Z","event":"telemetry_published","sequenceNo":42,"deviceId":"arduino-mkr-001"}
{"timestamp":"2026-04-24T00:00:02Z","event":"cmd_received","commandId":"550e8400...","type":"setLed"}
{"timestamp":"2026-04-24T00:00:03Z","event":"uart_parse_error","reason":"invalid json","raw":"..."}
{"timestamp":"2026-04-24T00:00:04Z","event":"offline_buffer_drop","dropped":1,"reason":"size_limit"}
```

共通フィールド: `timestamp`（UTC ISO 8601）、`event`、`deviceId`
追加フィールド: イベント種別ごとに `commandId`、`sequenceNo`、`reason` 等を付与

Docker ログ保持: `journalctl` デフォルト設定で直近 7 日分。

---

## 6. Web ダッシュボード設計

### 6.1 コマンド送信状態管理

```
idle → 送信中 → 反映待ち（10秒タイマー）
                    ├─ Telemetry 変化を確認 → 成功 → idle
                    └─ 10 秒超過 → 未到達警告表示 → idle
```

- 送信前に UUID v4 の `commandId` を生成して付与
- Telemetry の `ledState` / `intervalMs` フィールドで結果を確認

### 6.2 初回表示

- `telemetry` トピックは `Retain=true` のため、ブラウザ接続直後に最新値を受信できる
- `status` トピックも `Retain=true` のため、接続状態を即座に反映する

---

## 7. AWS リソース設計

### 7.1 リソース一覧

| リソース | 名前 | 管理 | 備考 |
|---------|------|------|------|
| IoT Thing | `arduino-mkr-001` | Terraform | デバイス論理表現 |
| IoT Certificate | 自動生成 | Terraform | X.509、`terraform/certs/` に出力（.gitignore 対象） |
| IoT Policy | `arduino-mkr-001-policy` | Terraform | デバイス用（publish/subscribe 制限） |
| Cognito Identity Pool | `arduino_iot_web_pool` | Terraform | 未認証ロール許可 |
| IAM Role | `arduino_iot_cognito_unauth` | Terraform | Web の MQTT subscribe + cmd publish 権限 |

### 7.2 IoT Policy（デバイス用）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-northeast-1:*:client/arduino-mkr-001"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": [
        "arn:aws:iot:ap-northeast-1:*:topic/device/arduino-mkr-001/telemetry",
        "arn:aws:iot:ap-northeast-1:*:topic/device/arduino-mkr-001/status"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["iot:Subscribe", "iot:Receive"],
      "Resource": [
        "arn:aws:iot:ap-northeast-1:*:topicfilter/device/arduino-mkr-001/cmd",
        "arn:aws:iot:ap-northeast-1:*:topic/device/arduino-mkr-001/cmd"
      ]
    }
  ]
}
```

### 7.3 Cognito 未認証ロール IAM ポリシー

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-northeast-1:*:client/web-*"
    },
    {
      "Effect": "Allow",
      "Action": ["iot:Subscribe", "iot:Receive"],
      "Resource": [
        "arn:aws:iot:ap-northeast-1:*:topicfilter/device/arduino-mkr-001/telemetry",
        "arn:aws:iot:ap-northeast-1:*:topicfilter/device/arduino-mkr-001/status",
        "arn:aws:iot:ap-northeast-1:*:topic/device/arduino-mkr-001/telemetry",
        "arn:aws:iot:ap-northeast-1:*:topic/device/arduino-mkr-001/status"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": "arn:aws:iot:ap-northeast-1:*:topic/device/arduino-mkr-001/cmd"
    }
  ]
}
```

> **セキュリティ注記（#12 対応）:** 未認証ロールに cmd publish 権限を与えているため、LAN 内の任意クライアントが制御コマンドを送信できる。本システムはプライベート LAN 内限定利用を前提とし、インターネット公開は行わない。将来的な公開時は Cognito ユーザープール認証（認証済みロール）へ移行すること。

---

## 8. セキュリティ設計

| 通信経路 | 認証方式 | 暗号化 |
|---------|---------|--------|
| Arduino → Gateway (UART) | なし（物理接続） | なし（ローカル） |
| Gateway → AWS IoT Core | X.509 クライアント証明書 | TLS 1.2+ |
| Web → AWS IoT Core | Cognito 一時クレデンシャル (SigV4) | TLS 1.2+ (WSS) |
| RPi Web サーバー → ブラウザ | なし（LAN 内 HTTP） | なし |

> Web サーバーが HTTP なのはプライベート LAN 内限定利用のため許容する。外部公開する場合はリバースプロキシで TLS 終端すること。

### 証明書管理

- デバイス証明書・秘密鍵は `terraform/certs/` に出力（`.gitignore` 対象）
- RPi 上では `/etc/arduino_iot/certs/` に `chmod 600` で配置
- Gateway コンテナには読み取り専用 volume mount で注入

**証明書漏えい時の対応手順:**
1. AWS IoT Core コンソール → 証明書を「無効化」→「削除」
2. `terraform apply` で新規証明書を再発行
3. 新証明書を RPi に配置（`scp` + `chmod 600`）
4. Gateway コンテナを再起動

---

## 9. デプロイ設計

図: `diagrams/deployment.puml`

### 9.1 Docker Compose 構成（RPi）

| サービス | イメージ | ポート | ボリューム | 再起動ポリシー |
|---------|---------|--------|-----------|--------------|
| `gateway` | ローカルビルド (arm/v7) | なし | `./certs:/app/certs:ro`（read-only）, `./.env` | `unless-stopped` |
| `web` | `nginx:alpine` | `8080:80` | `../web:/usr/share/nginx/html:ro` | `unless-stopped` |

### 9.2 ビルド・デプロイ手順概要

```
開発機で ARM クロスビルド
  → docker save / scp で RPi に転送
  → RPi で docker load → docker compose up -d
```

### 9.3 証明書配置手順（初回）

```bash
# 開発機（terraform apply 後）
scp terraform/certs/* raspberrypi:/etc/arduino_iot/certs/
ssh raspberrypi 'chmod 600 /etc/arduino_iot/certs/*'
```

---

## 10. エラー処理方針

| 障害 | Gateway の挙動 | Web の挙動 |
|------|-------------|-----------|
| UART 切断 | 5 秒間隔で再接続試行、ログ出力 | status → `degraded` 表示（タイマー15秒超） |
| MQTT 切断 | 指数バックオフで再接続、Telemetry を最大50件/10分バッファ | status → `offline` 表示（LWT） |
| JSON パースエラー | 改行まで読み飛ばして再同期、エラーログ出力 | 影響なし |
| 不正コマンド値 | ワーニングログ、UART 転送しない | 10秒後に未到達警告 |
| コマンド重複受信（QoS1） | commandId キャッシュで重複を検知し、UART 転送しない | 影響なし |
| コンテナ再起動 | オフラインバッファ消失（学習用途として許容、README 明記） | 接続状態はRe-subscribe後に復元 |

詳細なエラーシーケンスは詳細設計書に記載する。

---

## 付録: Codex レビュー対応記録（v1.1.0）

| 指摘 # | 対応 | 備考 |
|--------|------|------|
| #1 ランダムウォーク条件 | 対応: 第4章に追記 | |
| #2 EEPROM 永続化設計 | 対応: 第4章に追記 | |
| #3 オフラインバッファ不完全 | 対応: 第5章に10分上限・再送順序・ワーニング追記 | |
| #4 Retain 設定と初回表示の矛盾 | 対応: telemetry を Retain=true に変更 | |
| #5 commandId/タイムアウト未設計 | 対応: 第6章に Web 状態管理追記 | |
| #6 degraded 発行経路不在 | 対応: 第3章 status 規則・status_monitor モジュール追加 | |
| #7 Compose 再起動ポリシー未記載 | 対応: 第9章テーブルに追記 | |
| #8 非機能要件の設計化 | 対応: ログ仕様（第5章）を追加。性能測定は学習目的で省略 | |
| #9 UART フレーム破損回復 | 対応: 第3章に回復方針追記 | |
| #10 QoS1 重複対策 | 対応: 第3章に sequenceNo / commandId キャッシュ追記 | |
| #11 status 生成規則欠落 | 対応: 第3章 status publish 規則テーブル追加 | |
| #12 未認証ロールへの制御権限 | 対応: セキュリティ注記を追加し LAN 限定として許容を明記 | |
| #13 証明書漏えい手順 | 対応: 第8章に手順追記 | |
| #14 HTTP リスク | スキップ: LAN 内限定。外部公開時の注記を追記 | |
| #15 HTTP vs HTTPS | スキップ: #14 と同様 | |
| #16 コンテナ再起動でバッファ消失 | 対応: 第5章・第10章に「許容」と明記 | |
| #17 観測性不足 | 対応: 第5章にログフィールド例追記 | |
| #18 コスト超過ガード | スキップ: 学習用途、CloudWatch アラートは過剰 | |
| #19 監視フローに status なし | 対応: 第2章フロー図に status 並行フロー追記 | |
| #20 制御フロー異常系なし | 対応: 第2章制御フローに NG 分岐追記 | |
| #21 LWT と degraded の主体矛盾 | 対応: 第3章で LWT=offline 専用・degraded=タイマー通常 publish に分離 | |
