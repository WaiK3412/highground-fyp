"""Keep authentication endpoint tests independent of cached rate counters."""

from django.core.cache import cache
from django.test import TestCase


class ThrottleTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
