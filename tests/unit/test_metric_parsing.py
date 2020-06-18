import copy
from unittest import TestCase

from lib.m2ee.munin import (
    _populate_stats_by_java_version,
    _populate_stats_by_java_version_old,
    _standardize_memory_pools_output,
)


MENDIX_5_6_0_JAVA_7 = {
    "code": 2034048,
    "committed_heap": 518979584,
    "committed_nonheap": 37421056,
    "eden": 59097328,
    "init_heap": 536870912,
    "init_nonheap": 24313856,
    "max_heap": 518979584,
    "max_nonheap": 318767104,
    "permanent": 34661208,
    "survivor": 1599664,
    "tenured": 23388576,
    "used_heap": 84085568,
    "used_nonheap": 36695256,
}

MENDIX_6_5_0_JAVA_8_MEMORY_STATS = {
    "code": 19438080,
    "committed_heap": 2572681216,
    "committed_nonheap": 72876032,
    "eden": 43186320,
    "init_heap": 2684354560,
    "init_nonheap": 2555904,
    "max_heap": 2572681216,
    "max_nonheap": 1593835520,
    "permanent": 0,
    "survivor": 5704808,
    "tenured": 378924392,
    "used_heap": 401226288,
    "used_nonheap": 68329208,
}


MENDIX_6_JAVA_8_MEMORY_STATS = {
    "code": 0,
    "committed_heap": 2594897920,
    "committed_nonheap": 81747968,
    "eden": 0,
    "init_heap": 2684354560,
    "init_nonheap": 2555904,
    "max_heap": 2594897920,
    "max_nonheap": 780140544,
    "permanent": 0,
    "survivor": 0,
    "tenured": 0,
    "used_heap": 296124688,
    "used_nonheap": 76438224,
    "memorypools": [
        {
            "usage": 21603520,
            "index": 0,
            "name": "Code Cache",
            "is_heap": False,
        },
        {"usage": 48405720, "index": 1, "name": "Metaspace", "is_heap": False},
        {
            "usage": 6428984,
            "index": 2,
            "name": "Compressed Class Space",
            "is_heap": False,
        },
        {
            "usage": 242573808,
            "index": 3,
            "name": "Eden Space",
            "is_heap": True,
        },
        {
            "usage": 18051128,
            "index": 4,
            "name": "Survivor Space",
            "is_heap": True,
        },
        {
            "usage": 35499752,
            "index": 5,
            "name": "Tenured Gen",
            "is_heap": True,
        },
    ],
}

MENDIX_7_JAVA_8_STATS = {
    "code": 0,
    "committed_heap": 259522560,
    "committed_nonheap": 117194752,
    "eden": 0,
    "init_heap": 268435456,
    "init_nonheap": 2555904,
    "max_heap": 259522560,
    "max_nonheap": 780140544,
    "permanent": 0,
    "survivor": 0,
    "tenured": 0,
    "used_heap": 96604112,
    "used_nonheap": 112363696,
    "memorypools": [
        {
            "is_heap": False,
            "usage": 32141504,
            "name": "Code Cache",
            "index": 0,
        },
        {"is_heap": False, "usage": 71042872, "name": "Metaspace", "index": 1},
        {
            "is_heap": False,
            "usage": 9179320,
            "name": "Compressed Class Space",
            "index": 2,
        },
        {"is_heap": True, "usage": 53885928, "name": "Eden Space", "index": 3},
        {
            "is_heap": True,
            "usage": 3196408,
            "name": "Survivor Space",
            "index": 4,
        },
        {
            "is_heap": True,
            "usage": 39521776,
            "name": "Tenured Gen",
            "index": 5,
        },
    ],
}

MENDIX_8_JAVA_11_STATS = {
    "committed_heap": 518979584,
    "committed_nonheap": 153509888,
    "init_heap": 536870912,
    "init_nonheap": 7667712,
    "max_heap": 518979584,
    "max_nonheap": 780140544,
    "used_heap": 63055816,
    "used_nonheap": 125521336,
    "memorypools": [
        {
            "is_heap": False,
            "usage": 1299584,
            "name": "CodeHeap 'non-nmethods'",
            "index": 0,
        },
        {"is_heap": False, "usage": 90295136, "name": "Metaspace", "index": 1},
        {
            "is_heap": True,
            "usage": 35758560,
            "name": "Tenured Gen",
            "index": 2,
        },
        {
            "is_heap": False,
            "usage": 6269184,
            "name": "CodeHeap 'profiled nmethods'",
            "index": 3,
        },
        {"is_heap": True, "usage": 24701056, "name": "Eden Space", "index": 4},
        {
            "is_heap": True,
            "usage": 2596200,
            "name": "Survivor Space",
            "index": 5,
        },
        {
            "is_heap": False,
            "usage": 12353112,
            "name": "Compressed Class Space",
            "index": 6,
        },
        {
            "is_heap": False,
            "usage": 15304320,
            "name": "CodeHeap 'non-profiled nmethods'",
            "index": 7,
        },
    ],
}


class TestMetricParsingPerJavaVersion(TestCase):
    def test_java_8_memorypools(self):
        java_version = 8
        stats = {"memory": MENDIX_6_JAVA_8_MEMORY_STATS}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        self.assertEqual(old_stats, new_stats)

    def test_mendix_7_java_8_memorypools(self):
        java_version = 8
        stats = {"memory": MENDIX_7_JAVA_8_STATS}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        self.assertEqual(old_stats, new_stats)

    def test_mendix_6_no_memorypools(self):
        java_version = 8
        stats = {"memory": MENDIX_6_5_0_JAVA_8_MEMORY_STATS}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        self.assertEqual(old_stats, new_stats)

    def test_mendix_5_java_7_memory(self):
        """Test mendix 5.x runtime with java 7

        Mendix 5.x runtimes are not supported.

        So the new stats call would raise an exception,
        as opposed to the behavior in the old stats call.
        """
        java_version = 7
        stats = {"memory": MENDIX_5_6_0_JAVA_7}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )

        # new behavior is to raise an exception
        with self.assertRaises(RuntimeError):
            _populate_stats_by_java_version(copy.deepcopy(stats), java_version)

        # old behavior would simply return the stats as it is
        self.assertEqual(old_stats, stats)

    def test_mendix_8_java_11_memory_stats(self):
        java_version = 11
        stats = {"memory": MENDIX_8_JAVA_11_STATS}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        # Old stats were broken for Mendix 8, so this test is fairly useless,
        # but whatever.
        self.assertNotEqual(old_stats, new_stats)


class TestMemoryPoolParsing(TestCase):
    def test_java_11_combining(self):
        memory_pools = [
            {"usage": 11, "name": "CodeHeap 'non-nmethods'"},
            {"usage": 19, "name": "Metaspace"},
            {"usage": 7, "name": "Tenured Gen"},
            {"usage": 13, "name": "CodeHeap 'profiled nmethods'"},
            {"usage": 5, "name": "Eden Space"},
            {"usage": 3, "name": "Survivor Space"},
            {"usage": -1, "name": "Compressed Class Space"},
            {"usage": 17, "name": "CodeHeap 'non-profiled nmethods'"},
        ]
        correct_output = {
            "code": 11 + 13 + 17,
            "permanent": 19,
            "eden": 5,
            "survivor": 3,
            "tenured": 7,
        }
        self.assertEqual(
            correct_output,
            _standardize_memory_pools_output(memory_pools, java_version=11),
        )

    def test_java_8_combining(self):
        memory_pools = [
            {"usage": 3, "name": "Code Cache"},
            {"usage": 5, "name": "Metaspace"},
            {"usage": 7, "name": "Compressed Class Space"},
            {"usage": 11, "name": "Eden Space"},
            {"usage": 13, "name": "Survivor Space"},
            {"usage": 17, "name": "Tenured Gen"},
        ]
        correct_output = {
            "code": 3,
            "permanent": 5,
            "eden": 11,
            "survivor": 13,
            "tenured": 17,
        }
        self.assertEqual(
            correct_output,
            _standardize_memory_pools_output(memory_pools, java_version=8),
        )

    def test_memorypools_without_required_data_throw_error(self):
        memory_pools = [{"usage": 123, "name": "Nonsense"}]
        with self.assertRaises(RuntimeError):
            _standardize_memory_pools_output(memory_pools, java_version=8)

    def test_unsupported_java_version_raises(self):
        memory_pools = []
        java_version = 12
        with self.assertRaises(NotImplementedError):
            _standardize_memory_pools_output(memory_pools, java_version)
