import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    falkor_host: str = os.getenv("FALKOR_HOST", "localhost")
    falkor_port: int = int(os.getenv("FALKOR_PORT", "6379"))
    graph_name: str = os.getenv("GRAPH_NAME", "tracewire")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


settings = Settings()
