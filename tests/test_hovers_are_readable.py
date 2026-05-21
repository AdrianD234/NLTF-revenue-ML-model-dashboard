from __future__ import annotations

import pytest
from playwright.sync_api import Page

from test_filter_and_hover import (
    test_candidate_landscape_hover_is_human_readable as _assert_candidate_landscape_hover_is_human_readable,
    test_ensemble_hover_is_human_readable as _assert_ensemble_hover_is_human_readable,
    test_finalist_accuracy_hover_is_human_readable as _assert_finalist_accuracy_hover_is_human_readable,
    test_stress_hover_is_human_readable as _assert_stress_hover_is_human_readable,
)


pytestmark = pytest.mark.e2e


def test_candidate_landscape_hover_has_management_labels(page: Page) -> None:
    _assert_candidate_landscape_hover_is_human_readable(page)


def test_finalist_accuracy_hover_has_management_labels(page: Page) -> None:
    _assert_finalist_accuracy_hover_is_human_readable(page)


def test_ensemble_hover_has_management_labels(page: Page) -> None:
    _assert_ensemble_hover_is_human_readable(page)


def test_stress_hover_has_management_labels(page: Page) -> None:
    _assert_stress_hover_is_human_readable(page)
