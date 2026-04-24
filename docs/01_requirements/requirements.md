# 要件定義書

| 項目 | 内容 |
|------|------|
| プロジェクト名 | arduino_aws_iot |
| バージョン | 1.1.0 |
| 作成日 | 2026-04-24 |
| 最終更新 | 2026-04-24（Codex レビュー反映） |
| ステータス | Draft |

---

## 1. 目的・背景

### 1.1 目的

Arduino MKR Zero と Raspberry Pi を UART で接続し、Raspberry Pi から AWS IoT Core へ MQTT over TLS でデータを中継する IoT システムを構築する。Web ブラウザからリアルタイム監視と遠隔制御を可能にすることで、組み込み開発・MQTT プロトコル・AWS IoT サービスの実地学習を行う。

### 1.2 背景

- 手持ちハードウェア（Arduino MKR Zero / Raspberry Pi）を活用した成果物を GitHub で公開したい
- センサー類は未所持のため、疑似センサーデータ（ランダムウォーク）で代替する
- 個人開発・学習目的であるため、AWS コストを無料枠内に抑える

### 1.3 スコープ

| 対象 | 内容 |
|------|------|
| IN | Arduino ファームウェア / RPi Gateway / AWS IoT Core / Web ダッシュボード |
| OUT | モバイルアプリ / 複数デバイス管理 / 課金分析 / OTA アップデート |

本バージョンの対象デバイスは `arduino-mkr-001` の 1 台のみ。

---

## 2. ステークホルダー

| 役割 | 説明 |
|------|------|
| 開発者 / 運用者 | 本人（個人開発）。全工程を担当 |
| 学習目的利用者 | 本人。MQTT・AWS IoT・組み込み通信の学習 |

---

## 3. 機能要件

### F-01: 疑似センサーデータ送信

- Arduino MKR Zero は疑似温度・湿度データをランダムウォークアルゴリズムで生成し、JSON 形式で UART 送信する
- **ランダムウォークパラメータ:**
  - 温度: 初期値 25.0℃、範囲 15.0〜35.0℃、1 回の変動幅 ±0.5℃以内
  - 湿度: 初期値 50.0%、範囲 20.0〜80.0%、1 回の変動幅 ±1.0% 以内
  - 範囲超過時は境界値に丸める
- 送信間隔は **5〜30 秒** の範囲で設定可能とする（無料枠超過防止のため最小 5 秒）
- 送信間隔は変更時のみ EEPROM に書き込む（同値再設定は書き込まない）
- EEPROM 値が範囲外の場合はデフォルト値（10 秒）を使用する

### F-02: データ中継（UART → AWS IoT Core）

- Raspberry Pi 上の Gateway プロセスは Arduino からの UART データを受信し、以下の MQTT トピックへ publish する
  - `device/arduino-mkr-001/telemetry` — センサーデータ（Gateway が publish）
  - `device/arduino-mkr-001/status` — デバイス状態（Gateway が LWT として登録）
- MQTT 通信は TLS 1.2 以上、X.509 証明書認証を使用する
- **オフライン中のデータ扱い:** MQTT 切断中に受信した Telemetry は最大 50 件・最大 10 分分をメモリ上に保持し、再接続後に時系列順で再送する。上限超過時は古いデータから破棄しワーニングログを出力する

### F-03: リアルタイム Web 監視

- Web ブラウザから AWS IoT Core へ MQTT over WebSocket で接続し、センサーデータをリアルタイムで表示する
- **表示項目:** 温度・湿度・LED 状態・最終受信時刻（Gateway が MQTT publish した UTC 時刻）・デバイス接続状態
- Web 画面は直近 1 件の Telemetry をメモリ保持し、初回表示時に最新値を表示する
- Web ダッシュボードはプライベート LAN 内での利用を前提とし、インターネット公開は行わない

### F-04: Web からの遠隔制御

- Web ブラウザから Arduino の内蔵 LED（LED_BUILTIN）を ON/OFF できる
- Web ブラウザから Arduino の送信間隔（5〜30 秒）を変更できる
- 制御コマンドは Web → `device/arduino-mkr-001/cmd` → Gateway → UART → Arduino の経路で伝達する
- **コマンド確認:**
  - Web はコマンドごとに一意の `commandId`（UUID v4）を付与して publish する
  - Arduino はコマンド実行後に次の Telemetry で実行結果を反映する（ACK は Telemetry で確認）
  - Web は 10 秒以内に Telemetry の更新がない場合、コマンド未到達の可能性を UI に表示する
- **入力検証:** 範囲外の送信間隔（5 秒未満・30 秒超）は Gateway が拒否しワーニングログを出力、不正 JSON はパースエラーとして処理し UART へ転送しない

### F-05: 接続状態監視

- Gateway は MQTT 切断を検知し、指数バックオフ（1秒・2秒・4秒・8秒・最大 60 秒）で自動再接続する
- Gateway は UART 切断を検知し、5 秒間隔で再接続を試みる
- **オンライン/オフライン判定基準:**
  - `online`: Gateway が MQTT 接続中かつ直近 15 秒以内に Telemetry を受信
  - `degraded`: MQTT 接続中だが 15 秒超 Telemetry 未受信（Arduino 側の問題）
  - `offline`: Gateway が MQTT 切断（LWT により IoT Core がこのステータスを publish）
- Web ダッシュボードはデバイスのステータスを上記 3 状態で表示する

### F-06: コンテナ化デプロイ

- Gateway および Web サーバーは Docker Compose でコンテナ管理する
- コンテナは `restart: unless-stopped` で自動再起動する
- 証明書と `.env` は読み取り専用の volume mount で注入し、コンテナイメージには含めない

---

## 4. 非機能要件

### N-01: セキュリティ

- デバイス認証は X.509 クライアント証明書を用いる（ユーザー名/パスワード認証は使用しない）
- Web ブラウザ認証は Amazon Cognito Identity Pool（未認証ロール）を使用する
- IoT Policy は許可トピックを最小限に制限する（`device/arduino-mkr-001/*` のみ）
- 証明書・秘密鍵は Git リポジトリに含めない（`.gitignore` で除外）
- 証明書ファイルのパーミッションは `600`（オーナーのみ読み書き）とする
- **証明書漏えい時の対応:** AWS IoT Core コンソールで証明書を無効化・削除し、新規証明書を再発行して RPi に配置する。手順は `docs/` に記載する

### N-02: 可用性

- Gateway は障害後に自動復旧する（MQTT / UART の再接続機能）
- コンテナ停止時は Docker の再起動ポリシーにより自動起動する

### N-03: コスト

- AWS サービスの利用は無料枠の範囲内に収める
  - AWS IoT Core: 送信間隔 10 秒時 ≈ 月 259K メッセージ（無料枠 2.25M/月 の 12%）
  - Amazon Cognito: 月間 50K MAU まで無料
- 追加の有料サービス（DynamoDB / Lambda / S3）はスコープ外

### N-04: 保守性

- 環境変数は `.env` ファイルで一元管理し、コード内にハードコーディングしない
- IaC（Terraform）で AWS リソースを管理し、再現性を確保する
  - Terraform 管理対象: IoT Thing・IoT Policy・Cognito Identity Pool・IAM ロール
  - 証明書は `terraform apply` 時に自動生成し `terraform/certs/` に保存する（`.gitignore` 対象）
- README に初回セットアップ手順を記述する

### N-05: 性能

- UART 通信は 115,200 bps とする
- センサーデータの Web 表示遅延は目標 2 秒以内（MQTT 経由の伝搬遅延を含む）
- Gateway の CPU 使用率は Raspberry Pi 上で常時 10% 未満を目標とする

### N-06: ログ

- Gateway は以下のイベントを構造化ログ（JSON Lines）で stdout に出力する
  - MQTT 接続・切断・再接続
  - UART 接続・切断・再接続
  - Telemetry publish 成功・失敗
  - コマンド受信・UART 転送
  - 入力バリデーションエラー
  - オフラインバッファの破棄
- ログは Docker のデフォルト（journald）で管理し、直近 7 日分を保持する

---

## 5. MQTTトピック定義

| トピック | publish 者 | subscribe 者 | 内容 |
|---------|-----------|-------------|------|
| `device/arduino-mkr-001/telemetry` | Gateway | Web | センサーデータ（温度・湿度・LED 状態・送信間隔） |
| `device/arduino-mkr-001/status` | Gateway（LWT） | Web | デバイス接続状態（`online` / `degraded` / `offline`） |
| `device/arduino-mkr-001/cmd` | Web | Gateway | 制御コマンド（LED 制御・送信間隔変更） |

---

## 6. ペイロードスキーマ

### Telemetry（Arduino → Gateway → AWS IoT Core）

```json
{
  "schemaVersion": "1.0",
  "deviceId": "arduino-mkr-001",
  "timestamp": 1714000000000,
  "temperatureC": 23.4,
  "humidityPct": 55.2,
  "ledState": false,
  "intervalMs": 10000,
  "sequenceNo": 42
}
```

### Command（Web → AWS IoT Core → Gateway → UART）

```json
{
  "commandId": "550e8400-e29b-41d4-a716-446655440000",
  "type": "setLed",
  "value": true
}
```

```json
{
  "commandId": "550e8400-e29b-41d4-a716-446655440001",
  "type": "setInterval",
  "value": 10000
}
```

### Status（Gateway LWT）

```json
{ "state": "offline" }
```

---

## 7. 制約条件

| 制約 | 内容 |
|------|------|
| ハードウェア | Arduino MKR Zero（WiFi なし）/ Raspberry Pi（armv7 以上）/ センサーなし |
| 通信方式 | Arduino ↔ RPi 間は UART（USB シリアル）のみ |
| インターネット接続 | RPi は有線または Wi-Fi でインターネット接続済みであること |
| AWS アカウント | 有効な AWS アカウントおよび CLI 認証設定（`~/.aws/credentials`）が必要 |
| 開発環境 | Docker が動作する WSL2 または Linux（ARM 向けクロスビルド対応） |
| コスト上限 | AWS 費用は原則 0 円（無料枠内） |
| 開発期間 | 1〜2 日（約 12 時間）を想定 |
| 公開範囲 | Web ダッシュボードはプライベート LAN 内のみ |

---

## 8. 用語定義

| 用語 | 定義 |
|------|------|
| Arduino MKR Zero | Microchip SAMD21 ベースの Arduino ボード。本システムの末端デバイス |
| Raspberry Pi | シングルボードコンピュータ。Gateway として機能する |
| Gateway | RPi 上で動作し、UART と MQTT の相互変換を行う Python サービス |
| AWS IoT Core | Amazon Web Services が提供するマネージド MQTT ブローカーサービス |
| Thing | AWS IoT Core 上のデバイスの論理表現。本システムでは `arduino-mkr-001` |
| MQTT | Message Queuing Telemetry Transport。IoT 向け軽量パブサブプロトコル |
| LWT | Last Will and Testament。MQTT クライアントが異常切断時に自動送信するメッセージ |
| UART | Universal Asynchronous Receiver-Transmitter。Arduino と RPi 間のシリアル通信 |
| Telemetry | Arduino が送信する疑似センサーデータ（温度・湿度・状態情報） |
| Command | Web から Arduino へ送信する制御指示（LED 制御・送信間隔変更） |
| Cognito Identity Pool | AWS の ID 管理サービス。Web ブラウザへ一時的な AWS 認証情報を払い出す |
| Terraform | HashiCorp 製の IaC ツール。AWS リソースをコードで管理する |
| ランダムウォーク | 前回値に小さなランダム変動を加えて次の値を生成するアルゴリズム |

---

## 9. 前提・除外事項

### 前提

- Raspberry Pi は起動済みで SSH アクセス可能な状態にある
- Arduino IDE（または PlatformIO）が開発機にインストール済みであること
- AWS CLI が設定済みであること（`aws configure` 完了）
- Terraform CLI が開発機にインストール済みであること

### 除外事項

- Arduino と Raspberry Pi の初回配線手順（ハードウェアセットアップ）
- AWS アカウントの作成手順
- Raspberry Pi OS のインストール手順
- データの長期保存・分析（DynamoDB / Timestream 等）
- ユーザー認証付き Web UI（拡張候補として次フェーズで検討）
- 複数デバイス対応

---

## 付録: Codex レビュー対応記録（v1.1.0）

| 指摘 # | 対応 | 備考 |
|--------|------|------|
| #1 MQTT トピック未定義 | 対応: 第 5 章追加 | |
| #2 JSON スキーマ未定義 | 対応: 第 6 章追加 | |
| #3 ランダムウォーク定量条件 | 対応: F-01 に追記 | |
| #4 コマンド ACK/タイムアウト | 対応: F-04 に追記（Telemetry での確認方式を採用） | |
| #5 オンライン/オフライン判定 | 対応: F-05 に 3 状態定義を追加 | |
| #6 送信間隔とコスト矛盾 | 対応: 最小 5 秒に変更 | |
| #7 未認証ロールの制御リスク | スキップ: LAN 内限定利用のため許容。拡張候補として除外事項に記載 | |
| #8 証明書漏えい手順 | 対応: N-01 に追記 | |
| #9 オフライン中データ扱い | 対応: F-02 に追記 | |
| #10 遅延測定条件 | スキップ: 学習目的のため定量的測定基準は不要 | |
| #11 CPU 測定機種 | スキップ: 個人所有機で測定するため機種固定不要 | |
| #12 入力検証・異常値 | 対応: F-04 に追記 | |
| #13 EEPROM 耐久性 | 対応: F-01 に書き込み条件を追記 | |
| #14 最終受信時刻の基準 | 対応: F-03 に「Gateway が publish した UTC 時刻」と定義 | |
| #15 ログ要件 | 対応: N-06 を新設 | |
| #16 Terraform スコープ | 対応: N-04 に管理対象を明記 | |
| #17 認証情報注入方法 | スキップ: F-06 の volume mount 記述で対応済み | |
| #18 Web 初期表示 | 対応: F-03 に記載 | |
| #19 単一デバイス前提 | 対応: 1.3 スコープに追記 | |
| #20 優先順位分類 | スキップ: 個人プロジェクトのため不要 | |
