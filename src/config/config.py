import os
from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise EnvironmentError(f"環境変数 '{name}' が設定されていません。必須です。")
    return value


GCP_PROJECT_ID = require_env("GCP_PROJECT_ID")

SQL_GCS_URI = require_env("SQL_GCS_URI")
USE_LEGACY_SQL = os.getenv("USE_LEGACY_SQL", "false").lower() == "true"

CUSTOMER_ATTRIBUTE_ANALYSIS_PROMPT_URI = require_env(
    "CUSTOMER_ATTRIBUTE_ANALYSIS_PROMPT_URI"
)
CUSTOMER_APPROACH_RECOMMENDATION_PROMPT_URI = require_env(
    "CUSTOMER_APPROACH_RECOMMENDATION_PROMPT_URI"
)

SLACK_WEBHOOK_URL = require_env("SLACK_WEBHOOK_URL")
