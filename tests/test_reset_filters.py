from __future__ import annotations

import pytest
from playwright.sync_api import Page

from test_filter_and_hover import test_reset_filters_restores_defaults as _assert_reset_filters_restores_defaults


pytestmark = pytest.mark.e2e


def test_reset_filters_button_restores_default_chips(page: Page) -> None:
    _assert_reset_filters_restores_defaults(page)
