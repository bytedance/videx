# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

Regression tests for scoping NDV results to the requesting method.

Two defects are covered:

1. ``ndv_cache`` was keyed on ``(index_name, fields)`` only, so a value computed
   for one ``ndv_method`` was served to a later request that explicitly asked
   for a different method.
2. ``info_low()`` stored the per-request method on the shared model instance as
   ``self.ndv_method``. Model instances are reused across requests via
   ``VidexSingleton.model_cache_dict`` and the Flask server runs with
   ``threaded=True``, so concurrent requests could overwrite one another's
   method while an estimate was still being calculated.
"""
import threading
import unittest
from types import MethodType

from sub_platforms.sql_opt.videx.model.videx_model_innodb import VidexModelInnoDB


TABLE_ROWS = 1000
# Deterministic stand-ins for the real estimators.
STUB_NDV = {'scale': 10, 'GEE': 20}


def _build_request(ndv_method, index_name='idx_a', columns=('a',)):
    return {
        'item_type': 'videx_request',
        'properties': {
            'dbname': 'videx_test',
            'function': 'virtual int ha_videx::info_low(uint, bool)',
            'table_name': 'test_table',
            'target_storage_engine': 'INNODB',
            'videx_options': '{"ndv_method": "%s"}' % ndv_method,
        },
        'data': [{
            'item_type': 'key',
            'properties': {'key_length': '???', 'name': index_name},
            'data': [
                {'item_type': 'field',
                 'properties': {'name': c, 'store_length': '???'},
                 'data': []}
                for c in columns
            ],
        }],
    }


class _StubTableStats:
    """Minimal stand-in for the table stats object used by info_low()."""
    records = TABLE_ROWS
    clustered_index_size = 1
    sum_of_other_index_sizes = 0
    data_file_length = 1
    index_file_length = 1
    data_free_length = 0
    innodb_buffer_pool_size = 1
    table_name = 'test_table'

    def get_ideal_ndv(self, index_name, field_list):
        return None


class TestNdvMethodScoping(unittest.TestCase):
    def _make_model(self):
        model = VidexModelInnoDB.__new__(VidexModelInnoDB)
        from cachetools import TTLCache
        model.ndv_cache = TTLCache(maxsize=1000, ttl=1200)
        model.table_stats = _StubTableStats()
        model.pct_cached = 0
        model.df_sample_raw = None
        model.ndv_model = None
        model.calls = []

        def stub_ndv(self, index_name, field_list, ndv_method=None):
            self.calls.append(ndv_method)
            return STUB_NDV.get(ndv_method, 1)

        model.ndv = MethodType(stub_ndv, model)
        return model

    def test_cache_is_scoped_per_ndv_method(self):
        """A cached estimate must not be reused for a different ndv_method."""
        model = self._make_model()

        first = model.info_low(_build_request('scale'))
        second = model.info_low(_build_request('GEE'))

        # Both methods must actually be consulted.
        self.assertEqual(['scale', 'GEE'], model.calls)

        rpk_key = 'rec_per_key #@# idx_a #@# a'
        scale_rpk = first[rpk_key]
        gee_rpk = second[rpk_key]

        self.assertAlmostEqual(TABLE_ROWS / STUB_NDV['scale'], scale_rpk)
        self.assertAlmostEqual(TABLE_ROWS / STUB_NDV['GEE'], gee_rpk)
        self.assertNotEqual(scale_rpk, gee_rpk)

    def test_same_method_still_hits_cache(self):
        """Scoping the key must not defeat caching for repeated requests."""
        model = self._make_model()

        model.info_low(_build_request('scale'))
        model.info_low(_build_request('scale'))

        self.assertEqual(['scale'], model.calls,
                         'the second identical request should hit the cache')

    def test_concurrent_requests_do_not_leak_method(self):
        """Concurrent requests with different methods must not contaminate."""
        model = self._make_model()
        results = []
        lock = threading.Lock()

        def worker(i):
            method = ('scale', 'GEE')[i % 2]
            # Distinct index per call so every request is a cache miss.
            req = _build_request(method, index_name='idx_%d' % i)
            out = model.info_low(req)
            with lock:
                results.append((method, out['rec_per_key #@# idx_%d #@# a' % i]))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(40, len(results))
        for method, rec_per_key in results:
            self.assertAlmostEqual(
                TABLE_ROWS / STUB_NDV[method], rec_per_key,
                msg='request asking for %s received another method result' % method)


if __name__ == '__main__':
    unittest.main()
