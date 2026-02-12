import json
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
import vertexai

from google.cloud import storage, bigquery
from vertexai.generative_models import GenerativeModel
from src.config.logging_config import setup_logging
from src.config.config import (
    CUSTOMER_APPROACH_RECOMMENDATION_PROMPT_URI,
    CUSTOMER_ATTRIBUTE_ANALYSIS_PROMPT_URI,
    GCP_PROJECT_ID,
    SLACK_WEBHOOK_URL,
    SQL_GCS_URI,
    USE_LEGACY_SQL,
)

setup_logging()
logger = logging.getLogger(__name__)


def post_to_slack(message: str, webhook_url: str):
    """Slackにテキストメッセージを送信"""
    payload = {"text": message}

    res = requests.post(webhook_url, json=payload)

    if res.status_code != 200:
        logger.error(f"Slack webhook error: {res.text}")


def run_query(sql: str, project: str) -> pd.DataFrame:
    """BigQuery に SQL を投げて完了を待つ。戻り値は job 情報の dict"""
    bd_client = bigquery.Client(project=project)
    job_config = bigquery.QueryJobConfig()
    job_config.use_legacy_sql = USE_LEGACY_SQL

    query_job = bd_client.query(sql, job_config=job_config)

    return query_job.to_dataframe()


def read_text_from_gcs(uri: str) -> str:
    """引数で与えられた Google Cloud Storage URI からテキストを返す"""
    if not uri or not uri.startswith("gs://"):
        raise ValueError("The Google Cloud Storage URI must begin with 'gs://.'")

    # Google Cloud Storage URI を分解して、バケット名とファイル名を取得
    _, _, path = uri.partition("gs://")
    bucket_name, _, file_name = path.partition("/")

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)

    if not blob.exists():
        raise FileNotFoundError(f"{uri} not found")

    return blob.download_as_text()


def call_gemini_with_payload(
    prompt_template: str,
    placeholder_token: str,
    payload,
    project: str,
) -> str:
    """prompt_template 内の placeholder_token を payload の文字列表現で置き換えて Gemini を呼び出す。
    - payload が dict/list の場合: JSON文字列にして埋め込む
    - payload が str の場合: そのまま埋め込む
    """
    vertexai.init(project=project, location="asia-northeast1")
    model = GenerativeModel("gemini-2.5-pro")

    if isinstance(payload, str):
        payload_text = payload
    else:
        payload_text = json.dumps(payload, ensure_ascii=False)

    prompt = prompt_template.replace(placeholder_token, payload_text)

    response = model.generate_content(prompt)
    return response.text


def build_gemini_payload_from_df(df: pd.DataFrame) -> dict:
    # 実行年月・日時を取得する
    JST = timezone(timedelta(hours=+9), "JST")
    target_month = datetime.now(JST).strftime("%Y-%m")
    customers: list[dict] = []

    for _, row in df.iterrows():
        # --- months: [{year_month, count}] -> {"2025-09": 3, ...} ---
        months_dict: dict[str, int] = {}
        months_raw = row.get("months")
        if isinstance(months_raw, (list, tuple)):
            for m in months_raw:
                # BigQuery Row or dict の両方に対応
                year_month = (
                    m.get("year_month") if isinstance(m, dict) else m["year_month"]
                )
                count = m.get("count") if isinstance(m, dict) else m["count"]
                months_dict[str(year_month)] = int(count)

        # --- inquiry_type_count: [{inquiry_type, count}] -> dict ---
        inquiry_type_count: dict[str, int] = {}
        itypes_raw = row.get("inquiry_type_count")
        if isinstance(itypes_raw, (list, tuple)):
            for t in itypes_raw:
                inquiry_type = (
                    t.get("inquiry_type") if isinstance(t, dict) else t["inquiry_type"]
                )
                count = t.get("count") if isinstance(t, dict) else t["count"]
                inquiry_type_count[str(inquiry_type)] = int(count)

        # --- channel_count: [{channel, count}] -> dict ---
        channel_count: dict[str, int] = {}
        channels_raw = row.get("channel_count")
        if isinstance(channels_raw, (list, tuple)):
            for c in channels_raw:
                channel = c.get("channel") if isinstance(c, dict) else c["channel"]
                count = c.get("count") if isinstance(c, dict) else c["count"]
                channel_count[str(channel)] = int(count)

        # --- inquiries: list[struct] -> list[dict]（ISO文字列に整形） ---
        inquiries_list: list[dict] = []
        for i in row["inquiries"]:
            # BigQuery Row or dict の両対応
            def _get(obj, key):
                return obj.get(key) if isinstance(obj, dict) else obj[key]

            inq_ts = _get(i, "inquired_at")
            if hasattr(inq_ts, "isoformat"):
                inq_ts = inq_ts.isoformat()

            inquiries_list.append(
                {
                    "inquired_at": inq_ts,
                    "inquiry_year_month": _get(i, "inquiry_year_month"),
                    "channel": _get(i, "channel"),
                    "inquiry_type": _get(i, "inquiry_type"),
                    "subject": _get(i, "subject"),
                    "details": _get(i, "details"),
                    "agent_response": _get(i, "agent_response"),
                    "response_action": _get(i, "response_action"),
                    "next_action_type": _get(i, "next_action_type"),
                    "is_resolved": bool(_get(i, "is_resolved")),
                }
            )

        # --- 日付系を ISO 文字列に ---
        registered_at = row.get("registered_at")
        if hasattr(registered_at, "isoformat"):
            registered_at = registered_at.isoformat()

        last_inquired_at = row.get("last_inquired_at")
        if hasattr(last_inquired_at, "isoformat"):
            last_inquired_at = last_inquired_at.isoformat()

        # --- 顧客オブジェクトを構築 ---
        customer_obj = {
            "customer_id": str(row["customer_id"]),
            "customer_name": row.get("customer_name"),
            "age": int(row["age"]) if pd.notna(row.get("age")) else None,
            "prefecture": row.get("prefecture"),
            "registered_at": registered_at,
            "inquiry_summary": {
                "total_inquiries_last_3m": int(row["total_inquiries_last_3m"]),
                "months": months_dict,
                "inquiry_type_count": inquiry_type_count,
                "channel_count": channel_count,
                "resolved_count": int(row["resolved_count"]),
                "unresolved_count": int(row["unresolved_count"]),
                "last_inquired_at": last_inquired_at,
            },
            "inquiries": inquiries_list,
        }

        customers.append(customer_obj)

    payload = {
        "run_context": {
            "target_month": target_month,
            "lookback_months": 3,
        },
        "customers": customers,
    }

    return payload


def main():
    try:

        logger.info("Reading SQL from [%s] ...", SQL_GCS_URI)

        # Google Cloud Storage からSQLを取得
        sql = read_text_from_gcs(SQL_GCS_URI)

        logger.info("Executing SQL [len=%d chars] ...", len(sql))

        # BigQuery 上でクエリを実行し、データフレームを取得
        df = run_query(sql, project=GCP_PROJECT_ID)
        payload = build_gemini_payload_from_df(df)

        # Google Cloud Storage から顧客属性を定義するためのGemini用プロンプトを取得
        customer_attribute_analysis_prompt = read_text_from_gcs(
            CUSTOMER_ATTRIBUTE_ANALYSIS_PROMPT_URI
        )

        customer_attribute_analysis_result = call_gemini_with_payload(
            prompt_template=customer_attribute_analysis_prompt,
            placeholder_token="{payload_json}",
            payload=payload,
            project=GCP_PROJECT_ID,
        )

        logger.info(
            "Reading Prompt from [%s] ...", CUSTOMER_APPROACH_RECOMMENDATION_PROMPT_URI
        )

        # Google Cloud Storage から顧客へのアプローチを出力させるためのGemini用プロンプトを取得
        customer_approach_recommendation_prompt = read_text_from_gcs(
            CUSTOMER_APPROACH_RECOMMENDATION_PROMPT_URI
        )

        customer_approach_recommendation_result = call_gemini_with_payload(
            prompt_template=customer_approach_recommendation_prompt,
            placeholder_token="{attributes_json}",
            payload=customer_attribute_analysis_result,
            project=GCP_PROJECT_ID,
        )

        slack_message = (
            f"AI提案（テキスト出力）:\n{customer_approach_recommendation_result}"
        )

        logger.info("Sending Message to [%s] ...", SLACK_WEBHOOK_URL)
        # Slackの指定のチャンネルにGeminiの出力結果を送信
        post_to_slack(slack_message, SLACK_WEBHOOK_URL)

    except Exception:
        logger.exception("Failed to execute query")


if __name__ == "__main__":
    main()
