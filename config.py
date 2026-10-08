import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
MCP_SERVER_NAME: str = os.getenv("MCP_SERVER_NAME", "taskflow-mcp-server")
MCP_API_KEY: str = os.getenv("MCP_API_KEY", "")

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

DAILY_REMINDER_HOUR: int = int(os.getenv("DAILY_REMINDER_HOUR", "9"))
DAILY_REMINDER_MINUTE: int = int(os.getenv("DAILY_REMINDER_MINUTE", "0"))

if not DATABASE_URL:
    print("⚠️ WARNING: DATABASE_URL is not set. Please configure .env.")
