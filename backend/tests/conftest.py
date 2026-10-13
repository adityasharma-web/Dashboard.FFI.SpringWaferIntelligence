from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engine import combine_inspections, load_reference, read_inspection, valid_spring_keys  # noqa: E402

PRODUCT = "152-900530D"
GOLDEN_PATH = BACKEND / "tests" / "fixtures" / "golden.json"


@pytest.fixture(scope="session")
def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def reference():
    ref, center = load_reference(PRODUCT, BACKEND / "coordinates")
    return ref, center


@pytest.fixture(scope="session")
def example_data(reference) -> pd.DataFrame:
    ref, _ = reference
    keys = valid_spring_keys(ref)
    frames = [read_inspection(p, PRODUCT, keys) for p in sorted((BACKEND / "examples").glob("SYNTH_WAFER_*.csv"))]
    return combine_inspections(frames)


@pytest.fixture
def tiny_reference_dir(tmp_path: Path) -> Path:
    """A small CSV reference: product TEST-PROD, gangs 1-2 x springs 1-10, with parenthetical headers."""
    rows = []
    for die in (1, 2):
        for spring in range(1, 11):
            rows.append({"Die_Num (gang_number)": die, "Spring_Num (spring_number)": spring, "feature": "A",
                         "X": 10.0 * die + 0.5 * spring, "Y": 100.0 - 2.0 * spring})
    ref_dir = tmp_path / "coordinates"
    ref_dir.mkdir()
    pd.DataFrame(rows).to_csv(ref_dir / "TEST-PROD.csv", index=False)
    return ref_dir


def make_inspection(product: str, wafer: str, statuses: dict[tuple[int, int], str], *, omit: set[tuple[int, int]] = frozenset()) -> pd.DataFrame:
    """Build a CSV-schema inspection frame; ``statuses`` maps (die, spring) -> Good/Low/Med/Killer."""
    rows = []
    for (die, spring), status in statuses.items():
        if (die, spring) in omit:
            continue
        rows.append({"Product": product, "Wafer_ID": wafer, "Die_Num": die, "Spring_Num": spring,
                     "Defect": "N" if status == "Good" else "Y", "Defect_Severity": "" if status == "Good" else status})
    return pd.DataFrame(rows)
