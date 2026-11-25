"""应用配置：从环境变量 / .env 读取。"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    data_dir: str
    scripts_dir: str
    logs_dir: str
    db_path: str


def load_config() -> Settings:
    return Settings(
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.environ.get("LLM_MODEL", "deepseek-chat"),
        data_dir=os.environ.get("DATA_DIR", "data"),
        scripts_dir=os.environ.get("SCRIPTS_DIR", "scripts"),
        logs_dir=os.environ.get("LOGS_DIR", "logs/jobs"),
        db_path=os.environ.get("DB_PATH", "app.db"),
    )
