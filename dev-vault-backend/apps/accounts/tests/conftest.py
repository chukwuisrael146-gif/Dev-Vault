import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def isolated_account_throttles():
    cache.clear()
    yield
    cache.clear()
