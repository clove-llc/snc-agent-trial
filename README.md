# ローカル開発手順（GCP 認証 / Cloud Functions）

## 1. 開発準備

### 1.1 gcloud CLI 用の認証（実施済み前提）

以下のコマンドで **gcloud CLI 自体のログイン** を行います。

```bash
gcloud auth login --no-launch-browser
```

※ この認証は gcloud コマンド操作用です。

---

### 1.2 Application Default Credentials（ADC）を作成する

BigQuery / Cloud Storage / Vertex AI など
コードから GCP SDK を利用するために必須 の認証です。

以下のコマンドを実行し、表示された URL を Windows 側のブラウザ で開いて認証します。

```bash
gcloud auth application-default login --no-launch-browser
```

成功すると、次のようなメッセージが表示されます。

---

### 1.3 ADC が作成されたことを確認する

```bash
ls ~/.config/gcloud/application_default_credentials.json
```

ファイルが存在すれば OK です。

---

### 1.4 gcloud 設定の確認

```bash
gcloud auth list
gcloud config list
```

認証済みアカウントや、現在のプロジェクト設定が表示されることを確認します。

---

### 1.5 環境変数の設定

ルートフォルダ上に`.env`ファイルを用意し、ローカル実行時に必要な環境変数を設定します。

```bash
SQL_GCS_URI='データマートに対して実行するSQLのGCS URI'
PROJECT_ID='対象プロジェクトのID'
USE_LEGACY_SQL=false
SLACK_WEBHOOK_URL='Slack WebhookのURL'
CUSTOMER_ATTRIBUTE_ANALYSIS_PROMPT_URI='AI推論ステップ1のプロンプトのGCS URI'
CUSTOMER_APPROACH_RECOMMENDATION_PROMPT_URI='AI推論ステップ2のプロンプトのGCS URI'
```

---

### 1.6 仮想環境の作成

```bash
python3 -m venv .venv
```

---

### 1.7 依存関係のインストール

```bash
pip install -r requirements.txt
```

## 2. 開発時の検証フロー

### 2.1 仮想環境を有効化する

```bash
source .venv/bin/activate
```

---

### 2.2 Cloud Functions をローカルで起動する

```bash
functions-framework --target=execute_from_gcs --port=8080 --debug
```

---

### 2.3 ローカルエンドポイントにアクセスする

起動後、以下のようなログが表示されます。

```bash
Running on http://127.0.0.1:8080
```

この URL にアクセスすることで、Cloud Functions の処理をローカルで検証できます。
※ 認証系のエラーが出た場合は `1.2` の手順を再度行ってください。

---
