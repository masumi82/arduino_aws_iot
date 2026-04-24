# ユーザー対応事項（事前セットアップ）

> Claude が実装を進める前に、ユーザー側で対応が必要な項目をまとめています。  
> 実装開始前までに完了しておいてください。

---

## 1. AWS 関連

### 1-1. AWS アカウント・CLI 設定
- [ ] AWS アカウントが有効であることを確認
- [ ] AWS CLI をインストール（未導入の場合）
  ```bash
  # WSL2 / Linux
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip awscliv2.zip && sudo ./aws/install
  ```
- [ ] 認証情報を設定
  ```bash
  aws configure
  # AWS Access Key ID: （IAM ユーザーのアクセスキー）
  # AWS Secret Access Key: （シークレットキー）
  # Default region name: ap-northeast-1
  # Default output format: json
  ```
- [ ] 動作確認
  ```bash
  aws sts get-caller-identity
  ```

### 1-2. IAM 権限
- [ ] Terraform 実行用 IAM ユーザーまたはロールに以下のポリシーがアタッチされていること
  - `AWSIoTFullAccess`（または IoT Thing / Certificate / Policy の作成権限）
  - `AmazonCognitoPowerUser`（または Identity Pool 作成権限）
  - `IAMFullAccess`（または IAM ロール・ポリシーの作成権限）

> **補足:** 学習目的であれば `AdministratorAccess` を一時的に付与しても可。本番運用時は最小権限化を推奨。

---

## 2. Terraform 関連

### 2-1. Terraform CLI インストール
- [ ] Terraform CLI をインストール（バージョン 1.5 以上推奨）
  ```bash
  # WSL2 / Ubuntu
  wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
  sudo apt update && sudo apt install terraform
  terraform --version
  ```

---

## 3. Arduino MKR Zero 関連

### 3-1. Arduino IDE セットアップ
- [ ] Arduino IDE 2.x をインストール（Windows または WSL2 経由）
  - ダウンロード先: https://www.arduino.cc/en/software

### 3-2. MKR Zero ボードパッケージ追加
- [ ] Arduino IDE → ボードマネージャーで「Arduino SAMD Boards」をインストール
  1. ツール → ボード → ボードマネージャー
  2. 検索: `SAMD`
  3. 「Arduino SAMD Boards (32-bits ARM Cortex-M0+)」をインストール

### 3-3. 必要ライブラリのインストール
- [ ] ライブラリマネージャーで以下をインストール
  | ライブラリ名 | バージョン | 用途 |
  |-------------|-----------|------|
  | ArduinoJson | 7.x 以上 | JSON シリアライズ |

  操作: スケッチ → ライブラリをインクルード → ライブラリを管理

### 3-4. Arduino MKR Zero と Raspberry Pi の接続（配線）
- [ ] USB ケーブル（Micro-USB）で Arduino MKR Zero と Raspberry Pi を接続
  - Arduino の **USB ポート（Micro-USB）** → Raspberry Pi の **USB-A ポート**
  - この接続で UART（USB CDC シリアル）と 5V 給電を同時に行う
  - **追加配線は不要**（センサーなし、UART は USB 経由）

### 3-5. シリアルポート確認（Raspberry Pi 側）
- [ ] Raspberry Pi に SSH 接続後、デバイスを確認
  ```bash
  ls /dev/ttyACM*
  # → /dev/ttyACM0 が表示されれば OK
  ```
- [ ] ユーザーを dialout グループに追加（コンテナからアクセスするため）
  ```bash
  sudo usermod -aG dialout $USER
  # ログアウト → ログイン後に有効化
  ```

---

## 4. Raspberry Pi 関連

### 4-1. Docker のインストール
- [ ] Raspberry Pi OS（64bit 推奨）に Docker をインストール
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  # ログアウト → ログイン後に有効化
  docker --version
  ```

### 4-2. Docker Compose のインストール
- [ ] Docker Compose プラグインをインストール
  ```bash
  sudo apt install docker-compose-plugin
  docker compose version
  ```

### 4-3. インターネット接続確認
- [ ] 外部への HTTPS / MQTT 接続が可能であることを確認
  ```bash
  # AWS エンドポイントへの疎通確認（Terraform apply 後に実施）
  curl -I https://iot.ap-northeast-1.amazonaws.com
  ```

---

## 5. GitHub 関連

### 5-1. リポジトリ作成
- [ ] GitHub でリポジトリを作成（例: `arduino_aws_iot`）
  - 公開設定: Public（ポートフォリオ公開を前提）
  - .gitignore: なし（プロジェクト内のものを使用）
  - ライセンス: MIT 推奨

### 5-2. ローカルリポジトリ初期化
- [ ] Raspberry Pi または開発機でリポジトリを初期化
  ```bash
  cd /home/m-horiuchi/claude/arduino_aws_iot
  git init
  git remote add origin https://github.com/<your-username>/arduino_aws_iot.git
  git add .gitignore .env.example
  git commit -m "Initial commit: project scaffold"
  git push -u origin main
  ```

---

## 6. 開発環境（PC 側）

### 6-1. クロスビルド環境（コンテナビルド用）
- [ ] Docker が動作していること（WSL2 上）
  ```bash
  docker run --rm --platform linux/arm/v7 hello-world
  ```
  - 失敗する場合: `docker buildx` の multiplatform 設定を確認

---

## 進捗管理

| # | 項目 | 担当 | 状態 |
|---|------|------|------|
| 1-1 | AWS アカウント・CLI | ユーザー | |
| 1-2 | IAM 権限 | ユーザー | |
| 2-1 | Terraform CLI | ユーザー | |
| 3-1 | Arduino IDE | ユーザー | |
| 3-2 | MKR Zero ボードパッケージ | ユーザー | |
| 3-3 | ArduinoJson ライブラリ | ユーザー | |
| 3-4 | Arduino ↔ RPi USB 接続 | ユーザー | |
| 3-5 | シリアルポート確認 | ユーザー | |
| 4-1 | Docker インストール | ユーザー | |
| 4-2 | Docker Compose | ユーザー | |
| 4-3 | インターネット接続確認 | ユーザー | |
| 5-1 | GitHub リポジトリ作成 | ユーザー | |
| 5-2 | ローカルリポジトリ初期化 | ユーザー | |
| 6-1 | Docker クロスビルド確認 | ユーザー | |
