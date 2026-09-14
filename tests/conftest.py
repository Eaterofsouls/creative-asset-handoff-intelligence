import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "python" / "src"))

import pytest


@pytest.fixture
def examples_dir():
    return REPO_ROOT / "examples"


@pytest.fixture
def messy_project(examples_dir):
    return examples_dir / "messy_project"


@pytest.fixture
def test_cases_dir(examples_dir):
    return examples_dir / "test_cases"
