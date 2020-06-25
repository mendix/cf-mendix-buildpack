import copy
from unittest import TestCase
from unittest.mock import Mock

from lib.m2ee import smaps
from lib.m2ee.munin import (
    _populate_stats_by_java_version,
    _populate_stats_by_java_version_old,
    _standardize_memory_pools_output,
    augment_and_fix_stats,
)

# Memory stats from the runtime
# → client.runtime_statistics().get_feedback()["memory"]
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

MENDIX_8_JAVA_11_STATS_PARALLELGC = {
    "committed_heap": 514850816,
    "committed_nonheap": 107937792,
    "init_heap": 536870912,
    "init_nonheap": 7667712,
    "max_heap": 514850816,
    "max_nonheap": 780140544,
    "memorypools": [
        {
            "index": 0,
            "is_heap": False,
            "name": "CodeHeap 'non-nmethods'",
            "usage": 1270400,
        },
        {"index": 1, "is_heap": False, "name": "Metaspace", "usage": 73971168},
        {
            "index": 2,
            "is_heap": False,
            "name": "CodeHeap 'profiled " "nmethods'",
            "usage": 12205312,
        },
        {"index": 3, "is_heap": True, "name": "PS Old Gen", "usage": 25652192},
        {
            "index": 4,
            "is_heap": False,
            "name": "Compressed Class Space",
            "usage": 10990064,
        },
        {
            "index": 5,
            "is_heap": True,
            "name": "PS Survivor Space",
            "usage": 7899720,
        },
        {
            "index": 6,
            "is_heap": True,
            "name": "PS Eden Space",
            "usage": 83522232,
        },
        {
            "index": 7,
            "is_heap": False,
            "name": "CodeHeap 'non-profiled " "nmethods'",
            "usage": 2661760,
        },
    ],
    "used_heap": 117074144,
    "used_nonheap": 101099024,
}

MENDIX_6_JAVA_8_STATS_PARALLELGC = {
    "code": 0,
    "committed_heap": 514850816,
    "committed_nonheap": 57958400,
    "eden": 0,
    "init_heap": 536870912,
    "init_nonheap": 2555904,
    "max_heap": 514850816,
    "max_nonheap": 780140544,
    "memorypools": [
        {
            "index": 0,
            "is_heap": False,
            "name": "Code Cache",
            "usage": 10762368,
        },
        {"index": 1, "is_heap": False, "name": "Metaspace", "usage": 37685080},
        {
            "index": 2,
            "is_heap": False,
            "name": "Compressed Class Space",
            "usage": 5180720,
        },
        {
            "index": 3,
            "is_heap": True,
            "name": "PS Eden Space",
            "usage": 38463376,
        },
        {"index": 4, "is_heap": True, "name": "PS Survivor Space", "usage": 0},
        {"index": 5, "is_heap": True, "name": "PS Old Gen", "usage": 23152144},
    ],
    "permanent": 0,
    "survivor": 0,
    "tenured": 0,
    "used_heap": 61615520,
    "used_nonheap": 53631816,
}

MENDIX_8_JAVA_11_STATS_CONCMARKSWEEPGC = {
    "committed_heap": 528154624,
    "committed_nonheap": 107659264,
    "init_heap": 536870912,
    "init_nonheap": 7667712,
    "max_heap": 528154624,
    "max_nonheap": 780140544,
    "memorypools": [
        {
            "index": 0,
            "is_heap": False,
            "name": "CodeHeap 'non-nmethods'",
            "usage": 1271040,
        },
        {"index": 1, "is_heap": False, "name": "Metaspace", "usage": 73892272},
        {
            "index": 2,
            "is_heap": False,
            "name": "CodeHeap 'profiled " "nmethods'",
            "usage": 11977984,
        },
        {
            "index": 3,
            "is_heap": False,
            "name": "Compressed Class Space",
            "usage": 10985232,
        },
        {
            "index": 4,
            "is_heap": True,
            "name": "Par Eden Space",
            "usage": 3918912,
        },
        {
            "index": 5,
            "is_heap": True,
            "name": "Par Survivor Space",
            "usage": 5843056,
        },
        {
            "index": 6,
            "is_heap": False,
            "name": "CodeHeap 'non-profiled " "nmethods'",
            "usage": 2761600,
        },
        {
            "index": 7,
            "is_heap": True,
            "name": "CMS Old Gen",
            "usage": 33777304,
        },
    ],
    "used_heap": 43539272,
    "used_nonheap": 100888448,
}

MENDIX_8_JAVA_11_STATS_G1GC = {
    "committed_heap": 536870912,
    "committed_nonheap": 105177088,
    "init_heap": 536870912,
    "init_nonheap": 7667712,
    "max_heap": 536870912,
    "max_nonheap": 780140544,
    "memorypools": [
        {
            "index": 0,
            "is_heap": False,
            "name": "CodeHeap 'non-nmethods'",
            "usage": 1276032,
        },
        {
            "index": 1,
            "is_heap": False,
            "name": "Metaspace",
            "usage": 73520192,
        },
        {
            "index": 2,
            "is_heap": False,
            "name": "CodeHeap 'profiled " "nmethods'",
            "usage": 10392064,
        },
        {
            "index": 3,
            "is_heap": False,
            "name": "Compressed Class Space",
            "usage": 10979664,
        },
        {
            "index": 4,
            "is_heap": True,
            "name": "G1 Eden Space",
            "usage": 20971520,
        },
        {
            "index": 5,
            "is_heap": True,
            "name": "G1 Old Gen",
            "usage": 30598056,
        },
        {
            "index": 6,
            "is_heap": True,
            "name": "G1 Survivor Space",
            "usage": 6291456,
        },
        {
            "index": 7,
            "is_heap": False,
            "name": "CodeHeap 'non-profiled " "nmethods'",
            "usage": 2462464,
        },
    ],
    "used_heap": 57861032,
    "used_nonheap": 98630736,
}

MENDIX_6_JAVA_8_STATS_CONCMARKSWEEPGC = {
    "code": 0,
    "committed_heap": 528154624,
    "committed_nonheap": 57221120,
    "eden": 0,
    "init_heap": 536870912,
    "init_nonheap": 2555904,
    "max_heap": 528154624,
    "max_nonheap": 780140544,
    "memorypools": [
        {"index": 0, "is_heap": False, "name": "Code Cache", "usage": 9254400},
        {"index": 1, "is_heap": False, "name": "Metaspace", "usage": 37936456},
        {
            "index": 2,
            "is_heap": False,
            "name": "Compressed Class Space",
            "usage": 5207456,
        },
        {
            "index": 3,
            "is_heap": True,
            "name": "Par Eden Space",
            "usage": 62842368,
        },
        {
            "index": 4,
            "is_heap": True,
            "name": "Par Survivor Space",
            "usage": 8716280,
        },
        {
            "index": 5,
            "is_heap": True,
            "name": "CMS Old Gen",
            "usage": 15998320,
        },
    ],
    "permanent": 0,
    "survivor": 0,
    "tenured": 0,
    "used_heap": 87556968,
    "used_nonheap": 52398816,
}

MENDIX_6_JAVA_8_STATS_G1GC = {
    "code": 0,
    "committed_heap": 536870912,
    "committed_nonheap": 57614336,
    "eden": 0,
    "init_heap": 536870912,
    "init_nonheap": 2555904,
    "max_heap": 536870912,
    "max_nonheap": 780140544,
    "memorypools": [
        {
            "index": 0,
            "is_heap": False,
            "name": "Code Cache",
            "usage": 10222400,
        },
        {"index": 1, "is_heap": False, "name": "Metaspace", "usage": 37641984},
        {
            "index": 2,
            "is_heap": False,
            "name": "Compressed Class Space",
            "usage": 5181992,
        },
        {
            "index": 3,
            "is_heap": True,
            "name": "G1 Eden Space",
            "usage": 68157440,
        },
        {
            "index": 4,
            "is_heap": True,
            "name": "G1 Survivor Space",
            "usage": 6291456,
        },
        {"index": 5, "is_heap": True, "name": "G1 Old Gen", "usage": 13107208},
    ],
    "permanent": 0,
    "survivor": 0,
    "tenured": 0,
    "used_heap": 87556104,
    "used_nonheap": 53059800,
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

    def test_mendix_6_java_8_stats_parallelgc(self):
        java_version = 8
        stats = {"memory": MENDIX_6_JAVA_8_STATS_PARALLELGC}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        self.assertEqual(old_stats, new_stats)

    def test_mendix_6_java_8_stats_g1gc(self):
        java_version = 8
        stats = {"memory": MENDIX_6_JAVA_8_STATS_G1GC}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        self.assertEqual(old_stats, new_stats)

    def test_mendix_6_java_8_stats_concmarksweepgc(self):
        java_version = 8
        stats = {"memory": MENDIX_6_JAVA_8_STATS_CONCMARKSWEEPGC}
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

    def test_mendix_8_java_11_memory_stats_parallelgc(self):
        java_version = 11
        stats = {"memory": MENDIX_8_JAVA_11_STATS_PARALLELGC}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        # if we have reached here without any exception
        # means we do support the alternate memory pool names
        self.assertNotEqual(old_stats, new_stats)

    def test_mendix_8_java_11_memory_stats_g1gc(self):
        java_version = 11
        stats = {"memory": MENDIX_8_JAVA_11_STATS_PARALLELGC}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        # if we have reached here without any exception
        # means we do support the alternate memory pool names
        self.assertNotEqual(old_stats, new_stats)

    def test_mendix_8_java_11_memory_stats_concmarksweepgc(self):
        java_version = 11
        stats = {"memory": MENDIX_8_JAVA_11_STATS_CONCMARKSWEEPGC}
        old_stats = _populate_stats_by_java_version_old(
            copy.deepcopy(stats), java_version
        )
        new_stats = _populate_stats_by_java_version(
            copy.deepcopy(stats), java_version
        )
        # if we have reached here without any exception
        # means we do support the alternate memory pool names
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


class TestMemoryPoolAliases(TestCase):
    """Test for the variations in the pool names based on enabled GC."""

    def test_poolnames_serialgc(self):
        input = [
            {"usage": 3, "name": "Code Cache"},
            {"usage": 5, "name": "Metaspace"},
            {"usage": 7, "name": "Compressed Class Space"},
            {"usage": 11, "name": "Eden Space"},
            {"usage": 13, "name": "Survivor Space"},
            {"usage": 17, "name": "Tenured Gen"},
        ]
        expected = {
            "code": 3,
            "permanent": 5,
            "eden": 11,
            "survivor": 13,
            "tenured": 17,
        }
        self.assertEqual(
            expected, _standardize_memory_pools_output(input, java_version=8),
        )

    def test_poolnames_parallelgc(self):
        input = [
            {"usage": 3, "name": "Code Cache"},
            {"usage": 5, "name": "Metaspace"},
            {"usage": 7, "name": "Compressed Class Space"},
            {"usage": 11, "name": "PS Eden Space"},
            {"usage": 13, "name": "PS Survivor Space"},
            {"usage": 17, "name": "PS Old Gen"},
        ]
        expected = {
            "code": 3,
            "permanent": 5,
            "eden": 11,
            "survivor": 13,
            "tenured": 17,
        }
        self.assertEqual(
            expected, _standardize_memory_pools_output(input, java_version=8),
        )

    def test_poolnames_java11_parallel_gc(self):
        input = [
            {"usage": 11, "name": "CodeHeap 'non-nmethods'"},
            {"usage": 19, "name": "Metaspace"},
            {"usage": 7, "name": "PS Old Gen"},
            {"usage": 13, "name": "CodeHeap 'profiled nmethods'"},
            {"usage": 5, "name": "PS Eden Space"},
            {"usage": 3, "name": "PS Survivor Space"},
            {"usage": -1, "name": "Compressed Class Space"},
            {"usage": 17, "name": "CodeHeap 'non-profiled nmethods'"},
        ]
        expected = {
            "code": 11 + 13 + 17,
            "permanent": 19,
            "eden": 5,
            "survivor": 3,
            "tenured": 7,
        }
        self.assertEqual(
            expected, _standardize_memory_pools_output(input, java_version=11),
        )

    def test_poolnames_concmarksweepgc(self):
        input = [
            {"usage": 3, "name": "Code Cache"},
            {"usage": 5, "name": "Metaspace"},
            {"usage": 7, "name": "Compressed Class Space"},
            {"usage": 11, "name": "Par Eden Space"},
            {"usage": 13, "name": "Par Survivor Space"},
            {"usage": 17, "name": "CMS Old Gen"},
        ]
        expected = {
            "code": 3,
            "permanent": 5,
            "eden": 11,
            "survivor": 13,
            "tenured": 17,
        }
        self.assertEqual(
            expected, _standardize_memory_pools_output(input, java_version=8),
        )

    def test_poolnames_g1gc(self):
        input = [
            {"usage": 3, "name": "Code Cache"},
            {"usage": 5, "name": "Metaspace"},
            {"usage": 7, "name": "Compressed Class Space"},
            {"usage": 11, "name": "G1 Eden Space"},
            {"usage": 13, "name": "G1 Survivor Space"},
            {"usage": 17, "name": "G1 Old Gen"},
        ]
        expected = {
            "code": 3,
            "permanent": 5,
            "eden": 11,
            "survivor": 13,
            "tenured": 17,
        }
        self.assertEqual(
            expected, _standardize_memory_pools_output(input, java_version=8),
        )


class TestAugmentStats(TestCase):
    def test_unused_heap_java8(self):
        """Test unused heap calculations for Java 8.

        Ensure for Java 8;
        - free java heap equals (committed - used)
        """
        stats = {}
        java_version = 8
        mock_smaps_output = {
            0: 19460,
            1: 71640,
            2: 193744,
            3: 3216,
            4: 0,
            5: 92176,
            6: 0,
        }

        smaps.get_smaps_rss_by_category = Mock(return_value=mock_smaps_output)

        # Check for following Java 8 scenarios:
        # - with and without memorypools
        # - with parallelGC
        for mem_stats in [
            MENDIX_6_JAVA_8_MEMORY_STATS,
            MENDIX_6_5_0_JAVA_8_MEMORY_STATS,
            MENDIX_6_JAVA_8_STATS_PARALLELGC,
        ]:
            stats["memory"] = mem_stats
            mock_threadpool_stats = {
                "threads_priority": 0,
                "max_threads": 0,
                "min_threads": 0,
                "max_idle_time_s": 0,
                "max_queued": -0,
                "threads": 0,
                "idle_threads": 0,
                "max_stop_time_s": 0,
            }
            new_stats = _populate_stats_by_java_version(
                copy.deepcopy(stats), java_version
            )
            new_stats["threadpool"] = mock_threadpool_stats
            fixed_stats = augment_and_fix_stats(new_stats, 0, java_version)
            javaheap = fixed_stats["memory"]["javaheap"]
            self.assertEqual(
                javaheap,
                (
                    stats["memory"]["committed_heap"]
                    - stats["memory"]["used_heap"]
                ),
            )

    def test_unused_heap_java11(self):
        """Test unused heap calculations for Java 11.

        Ensure for Java 11;
        - free java heap equals (committed - used)
        """
        java_version = 11
        stats = {}
        mock_smaps_output = {
            0: 19460,
            1: 71640,
            2: 193744,
            3: 3216,
            4: 0,
            5: 92176,
            6: 0,
        }

        smaps.get_smaps_rss_by_category = Mock(return_value=mock_smaps_output)

        # Check for following Java 11 scenarios:
        # - with serialgc
        # - with parallelGC
        for mem_stats in [
            MENDIX_8_JAVA_11_STATS,
            MENDIX_8_JAVA_11_STATS_PARALLELGC,
        ]:
            stats["memory"] = mem_stats
            mock_threadpool_stats = {
                "threads_priority": 0,
                "max_threads": 0,
                "min_threads": 0,
                "max_idle_time_s": 0,
                "max_queued": -0,
                "threads": 0,
                "idle_threads": 0,
                "max_stop_time_s": 0,
            }
            new_stats = _populate_stats_by_java_version(
                copy.deepcopy(stats), java_version
            )
            new_stats["threadpool"] = mock_threadpool_stats
            fixed_stats = augment_and_fix_stats(new_stats, 0, java_version)
            javaheap = fixed_stats["memory"]["javaheap"]
            self.assertEqual(
                javaheap,
                (
                    stats["memory"]["committed_heap"]
                    - stats["memory"]["used_heap"]
                ),
            )
