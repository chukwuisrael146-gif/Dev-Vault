import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clean_abuse_counters():
    cache.clear()
    yield
    cache.clear()
