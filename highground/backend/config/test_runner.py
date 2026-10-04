"""Use Django's documented test speed-up: the default hasher is slow by design.

These tests check authentication, not hashing strength. The override is scoped to
the test environment; production hashing is unchanged and cached hashers reset.
"""

from django.test import override_settings
from django.test.runner import DiscoverRunner


class FastPasswordTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._password_hashers = override_settings(
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
        )
        self._password_hashers.enable()

    def teardown_test_environment(self, **kwargs):
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            self._password_hashers.disable()
