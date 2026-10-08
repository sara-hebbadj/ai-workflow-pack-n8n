import json

import pytest

from workflow_pack.common import SeenStore
from workflow_pack.config import DATA_DIR, Paths


@pytest.fixture
def paths(tmp_path):
    return Paths(outputs=tmp_path / "outputs", logs=tmp_path / "logs")


@pytest.fixture
def store(tmp_path):
    return SeenStore(tmp_path / "state.sqlite")


def load_jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA_DIR / name).read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session")
def enquiries():
    return load_jsonl("enquiries.jsonl")


@pytest.fixture(scope="session")
def tickets():
    return load_jsonl("tickets.jsonl")


@pytest.fixture(scope="session")
def invoices():
    return load_jsonl("invoices/labels.jsonl")
