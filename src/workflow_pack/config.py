"""Paths and settings.

Secrets live in `Portfolio Projects/.env` (two folders above this repo), never in the repo.
Environment variables are used as a fallback, so CI and Docker work without a .env file.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas"
PROMPTS_DIR = REPO_ROOT / "prompts"
DATA_DIR = REPO_ROOT / "data"
WORKFLOWS_DIR = REPO_ROOT / "workflows"

# Business thresholds. The same values are set in each n8n workflow's "Config" node.
CONFIDENCE_THRESHOLD = 0.6  # enquiries and tickets below this go to a human
INVOICE_MIN_CONFIDENCE = 0.8  # invoices are stricter: money is involved
MONEY_TOLERANCE = 0.01  # allowed rounding difference, in currency units


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model_main: str
    model_cheap: str
    model_judge: str

    def model_for(self, role: str) -> str:
        return {"main": self.model_main, "cheap": self.model_cheap, "judge": self.model_judge}[role]


def load_settings() -> Settings:
    """Read `Portfolio Projects/.env` if it exists, then the environment."""
    env_file = REPO_ROOT.parents[1] / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
    return Settings(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        model_main=os.getenv("MODEL_MAIN", ""),
        model_cheap=os.getenv("MODEL_CHEAP", ""),
        model_judge=os.getenv("MODEL_JUDGE", ""),
    )


@dataclass(frozen=True)
class Paths:
    """Where the mock "sheets", queues and logs are written.

    In production these would be Google Sheets, Slack and an email service.
    For the demo they are CSV files so anyone can open them.
    """

    outputs: Path
    logs: Path

    @property
    def errors_csv(self) -> Path:
        return self.logs / "errors.csv"

    @property
    def state_db(self) -> Path:
        return self.outputs / "state.sqlite"


def default_paths() -> Paths:
    return Paths(outputs=REPO_ROOT / "outputs", logs=REPO_ROOT / "logs")
