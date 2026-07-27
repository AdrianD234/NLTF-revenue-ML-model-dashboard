from __future__ import annotations

from pathlib import Path

import pytest

# Screenshots are produced by a browser verification session and are not
# rebuildable from committed content, so these are developer-local scratch
# rather than clean-clone assurance.

pytestmark = pytest.mark.requires_local_scratch



def test_page_screenshots_exist() -> None:
    shots = list((Path(__file__).resolve().parents[1] / "artifacts" / "screenshots").glob("*.png"))
    names = [shot.name.lower() for shot in shots]

    assert len(shots) >= 8
    assert any("overview" in name for name in names)
    assert any("diagnostics" in name for name in names)
    assert any("scenario" in name for name in names)
    assert any("schiff" in name for name in names)
