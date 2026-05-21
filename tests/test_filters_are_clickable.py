from __future__ import annotations

import pytest
from playwright.sync_api import Page

from test_filter_and_hover import (
    test_all_primary_filter_dropdowns_open as _assert_all_primary_filter_dropdowns_open,
    test_primary_filters_are_clickable as _assert_primary_filters_are_clickable,
)


pytestmark = pytest.mark.e2e


def test_visible_primary_filters_are_directly_clickable(page: Page) -> None:
    _assert_primary_filters_are_clickable(page)


def test_visible_primary_dropdowns_open_without_more_button(page: Page) -> None:
    _assert_all_primary_filter_dropdowns_open(page)
