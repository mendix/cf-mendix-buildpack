#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import sys

CATEGORY_CODE = 0
CATEGORY_NATIVE_HEAP_ARENA = 1
CATEGORY_JVM_HEAP = 2
CATEGORY_THREAD_STACK = 3
CATEGORY_JAR = 4
CATEGORY_OTHER = 5
CATEGORY_NONE = 6

categories = (
    CATEGORY_CODE,
    CATEGORY_NATIVE_HEAP_ARENA,
    CATEGORY_JVM_HEAP,
    CATEGORY_THREAD_STACK,
    CATEGORY_JAR,
    CATEGORY_OTHER,
    CATEGORY_NONE,
)

STAGE_BORK = -1
STAGE_CODE = 0
STAGE_SEEN_NATIVE_HEAP = 1
STAGE_IN_JVM_HEAP = 2
STAGE_SEEN_JVM_HEAP = 3


class Smap:
    def __init__(self):
        self.vm_start = None
        self.vm_end = None
        self.flags = None
        self.inode = None
        self.descr = None
        self.size = None
        self.rss = None
        self.swap = None

        self.category = None

    def line(self, line):
        fields = line.split()
        if fields[0].endswith(":"):
            if fields[0] == "Size:":
                self.size = int(fields[1])
            elif fields[0] == "Rss:":
                self.rss = int(fields[1])
            elif fields[0] == "Swap:":
                self.swap = int(fields[1])
        else:
            (self.vm_start, self.vm_end) = fields[0].split("-")
            self.flags = fields[1]
            self.inode = int(fields[4])
            if len(fields) > 5:
                self.descr = fields[5]

    def __str__(self):
        return "%s %s-%s %s kB, %s %s kB %s kB %s %s" % (
            self.category,
            self.vm_start,
            self.vm_end,
            self.size,
            self.flags,
            self.rss,
            self.swap,
            self.inode,
            self.descr,
        )


def has_smaps(pid):
    return _load_proc_smaps_lines(pid) is not None


def get_smaps_rss_by_category(pid):
    lines = _load_proc_smaps_lines(pid)
    if lines is None:
        return None
    smaps = _parse_lines_to_smaps(lines)
    smaps = _educated_guess_category(smaps)
    return _get_rss_by_category(smaps)


def _load_proc_smaps_lines(pid):
    try:
        return open("/proc/%s/smaps" % pid).read().splitlines()
    except EnvironmentError:
        return None


def _parse_lines_to_smaps(lines):
    smaps = []
    smap = None
    for line in lines:
        if not line.split()[0].endswith(":"):
            smap = Smap()
            smaps.append(smap)
        smap.line(line)
    return smaps


def _educated_guess_category(smaps, debug=False):
    num_smaps = len(smaps)
    stage = STAGE_CODE
    i = 0
    while i < num_smaps:
        smap = smaps[i]

        if stage == STAGE_CODE:
            if smap.inode != 0 and smap.descr is not None:
                smap.category = CATEGORY_CODE
            elif smap.inode == 0 and smap.descr == "[heap]":
                smap.category = CATEGORY_NATIVE_HEAP_ARENA
                stage = STAGE_SEEN_NATIVE_HEAP
            else:
                stage = STAGE_BORK
        elif stage == STAGE_SEEN_NATIVE_HEAP:
            if smap.flags.startswith("rw") and smap.inode == 0:
                smap.category = CATEGORY_JVM_HEAP
                stage = STAGE_IN_JVM_HEAP
            else:
                stage = STAGE_BORK
        elif stage == STAGE_IN_JVM_HEAP:
            if smap.inode == 0 and smap.vm_start == smaps[i - 1].vm_end:
                smap.category = CATEGORY_JVM_HEAP
            else:
                stage = STAGE_SEEN_JVM_HEAP
        if stage == STAGE_SEEN_JVM_HEAP:
            if (
                smap.inode != 0
                and smap.descr is not None
                and smap.flags == "r-xp"
            ):
                smap.category = CATEGORY_CODE
            elif (
                i > 0
                and smap.inode != 0
                and smap.inode == smaps[i - 1].inode
                and smap.descr is not None
                and smap.descr == smaps[i - 1].descr
            ):
                smap.category = smaps[i - 1].category
            elif smap.inode == 0 and smap.descr == "[heap]":
                smap.category = CATEGORY_NATIVE_HEAP_ARENA
            elif (
                smap.inode == 0
                and smap.descr is not None
                and smap.descr.startswith("[stack")
            ):
                smap.category = CATEGORY_THREAD_STACK
            elif (
                i + 1 < len(smaps)
                and smap.vm_end == smaps[i + 1].vm_start
                and smap.rss != 0
                and smaps[i + 1].rss == 0
                and (smap.size + smaps[i + 1].size) % 65536 == 0
                and smap.inode == 0
                and smaps[i + 1].inode == 0
            ):
                smap.category = CATEGORY_NATIVE_HEAP_ARENA
                smaps[i + 1].category = CATEGORY_NATIVE_HEAP_ARENA
                i = i + 1
            elif (
                smap.flags.startswith("rw")
                and smap.inode == 0
                and i > 0
                and smaps[i - 1].flags.startswith("---")
                and smaps[i - 1].inode == 0
                and smap.size + smaps[i - 1].size == 1028
            ):
                smap.category = CATEGORY_THREAD_STACK
            elif smap.flags.startswith("---") and smap.rss == 0:
                smap.category = CATEGORY_NONE
            elif (
                smap.flags.startswith("r-")
                and smap.descr is not None
                and smap.descr.endswith("jar")
            ):
                smap.category = CATEGORY_JAR
            else:
                smap.category = CATEGORY_OTHER

        if debug:
            print(smap)
        i = i + 1
    return smaps


def _get_rss_by_category(smaps):
    result = {}
    for category in categories:
        result[category] = sum(
            [smap.rss for smap in [x for x in smaps if x.category == category]]
        )
    return result


if __name__ == "__main__":
    lines = sys.stdin.read().splitlines()
    smaps = _parse_lines_to_smaps(lines)
    smaps = _educated_guess_category(smaps, debug=True)
    totals = _get_rss_by_category(smaps)

    print("Native code: %s kB" % totals[CATEGORY_CODE])
    print(
        "Native heap and memory arenas: %s kB"
        % totals[CATEGORY_NATIVE_HEAP_ARENA]
    )
    print("JVM Heap: %s kB" % totals[CATEGORY_JVM_HEAP])
    print("Thread stacks: %s kB" % totals[CATEGORY_THREAD_STACK])
    print("JAR files: %s kB" % totals[CATEGORY_JAR])
    print("Other: %s kB" % totals[CATEGORY_OTHER])
