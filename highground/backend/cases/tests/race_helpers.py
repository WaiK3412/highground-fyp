"""Shared real-connection race helpers; this module contains no tests."""

import threading

from django.db import connection


def race(*requests):
    """Run each zero-argument callable in its own thread, released together."""
    barrier = threading.Barrier(len(requests))
    results = [None] * len(requests)

    def run(index, request):
        try:
            barrier.wait()
            results[index] = request()
        finally:
            connection.close()  # this thread's own connection

    threads = [threading.Thread(target=run, args=(i, r)) for i, r in enumerate(requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


class GazetteerReloadMixin:
    """TransactionTestCase empties every table, including the villages that
    migration 0008 loaded. Reload them so later tests and --keepdb reruns find them."""

    @classmethod
    def tearDownClass(cls):
        from importlib import import_module

        from django.apps import apps

        import_module("cases.migrations.0008_load_kelantan_locations").load(apps, None)
        super().tearDownClass()
