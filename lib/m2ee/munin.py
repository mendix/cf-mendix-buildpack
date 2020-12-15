#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import itertools
import os
import string
import warnings

from m2ee.log import logger
from . import smaps

# Use json if available. If not (python 2.5) we need to import the simplejson
# module instead, which has to be available.
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError as ie:
        logger.critical(
            "Failed to import json as well as simplejson. If "
            "using python 2.5, you need to provide the simplejson "
            "module in your python library path."
        )
        raise


default_stats = {
    "languages": ["en_US"],
    "entities": 0,
    "threadpool": {
        "threads_priority": 0,
        "max_threads": 0,
        "min_threads": 0,
        "max_idle_time_s": 0,
        "max_queued": -0,
        "threads": 0,
        "idle_threads": 0,
        "max_stop_time_s": 0,
    },
    "memory": {
        "init_heap": 0,
        "code": 0,
        "used_heap": 0,
        "survivor": 0,
        "max_nonheap": 0,
        "committed_heap": 0,
        "tenured": 0,
        "permanent": 0,
        "used_nonheap": 0,
        "eden": 0,
        "init_nonheap": 0,
        "committed_nonheap": 0,
        "max_heap": 0,
    },
    "sessions": {
        "named_users": 0,
        "anonymous_sessions": 0,
        "named_user_sessions": 0,
        "user_sessions": {},
    },
    "requests": {
        "": 0,
        "debugger/": 0,
        "ws/": 0,
        "xas/": 0,
        "ws-doc/": 0,
        "file": 0,
    },
    "cache": {"total_count": 0, "disk_count": 0, "memory_count": 0},
    "jetty": {
        "max_idle_time_s": 0,
        "current_connections": 0,
        "max_connections": 0,
        "max_idle_time_s_low_resources": 0,
    },
    "connectionbus": {
        "insert": 0,
        "transaction": 0,
        "update": 0,
        "select": 0,
        "delete": 0,
    },
}


def print_config(m2ee, name):
    stats, java_version = get_stats("config", m2ee.client, m2ee.config)
    if stats is None:
        return
    options = m2ee.config.get_munin_options()

    print_requests_config(name, stats)
    print_connectionbus_config(name, stats)
    print_sessions_config(
        name, stats, options.get("graph_total_named_users", True)
    )
    print_jvmheap_config(name, stats)
    print_threadpool_config(name, stats)
    print_cache_config(name, stats)
    print_jvm_threads_config(name, stats)
    print_jvm_process_memory_config(name)


def print_values(m2ee, name):
    stats, java_version = get_stats("values", m2ee.client, m2ee.config)
    if stats is None:
        return
    stats = augment_and_fix_stats(stats, m2ee.runner.get_pid(), java_version)
    options = m2ee.config.get_munin_options()

    print_requests_values(name, stats)
    print_connectionbus_values(name, stats)
    print_sessions_values(
        name, stats, options.get("graph_total_named_users", True)
    )
    print_jvmheap_values(name, stats)
    print_threadpool_values(name, stats)
    print_cache_values(name, stats)
    print_jvm_threads_values(name, stats)
    print_jvm_process_memory_values(
        name, stats, m2ee.runner.get_pid(), m2ee.client, java_version
    )


def guess_java_version(client, runtime_version, stats):
    m2ee_response = client.about()
    return _guess_java_version(m2ee_response, runtime_version, stats)


def _get_jre_major_version_from_version_string(version_string):
    """Java changed their versioning scheme for JRE/JDK greater than 9,
    as per https://openjdk.java.net/jeps/223
    """
    # *_ captures all remaining tuple elements
    major, minor, *_ = version_string.split(".")
    if major == "1":
        return int(minor)
    return int(major)


def _guess_java_version(m2ee_response, runtime_version, m2ee_stats):
    # type: ("lib.m2ee.client.M2EEResponse", "lib.m2ee.version.MXVersion", dict) -> "Optional[int]"
    """"This internal function has a more unit-testable API than
    `guess_java_version`, which enables us to preserve compatibility, whilst
    simultaneously adding unit testing.
    """
    if not m2ee_response.has_error():
        about = m2ee_response.get_feedback()
        if "java_version" in about:
            java_version_string = about["java_version"]
            return _get_jre_major_version_from_version_string(
                java_version_string
            )

    # This happens for some older Mendix 6 versions, but not all, the
    # java_version field was added somewhere between Mendix 6.5 (not present)
    # and Mendix 6.10.10 (present). The exact version that it was added in
    # is probably not important.
    # Anyway, all Mendix 6 runtimes run on Java 8.
    if runtime_version.major == 6:
        return 8

    # This branch should never be reached for Mendix versions in the Mendix
    # Cloud, see also https://github.com/mendix/m2ee-tools/issues/51
    if runtime_version.major == 5:
        m = m2ee_stats["memory"]
        if m["used_nonheap"] - m["code"] - m["permanent"] == 0:
            return 7
        return 8

    # If we have reached here, just return none as we were not
    # able to guess the java version based on the available data.
    return None


def get_stats(action, client, config):
    # place to store last known good statistics result to be used for munin
    # config when the app is down or b0rked
    options = config.get_munin_options()
    config_cache = options.get(
        "config_cache",
        os.path.join(
            config.get_default_dotm2ee_directory(), "munin-cache.json"
        ),
    )

    # TODO: even better error/exception handling
    stats = None
    java_version = None
    try:
        stats, java_version = get_stats_from_runtime(client, config)
        write_last_known_good_stats_cache(stats, config_cache)
    except Exception as e:
        if action == "config":
            logger.debug("Error fetching runtime/server statistics: %s", e)
            stats = read_stats_from_last_known_good_stats_cache(config_cache)
            if stats is None:
                stats = default_stats
        else:
            # assume something bad happened, like
            # socket.error: [Errno 111] Connection refused
            logger.error("Error fetching runtime/server statistics: %s", e)
    return stats, java_version


def get_stats_from_runtime(client, config):
    stats = {}
    logger.debug("trying to fetch runtime/server statistics")
    m2eeresponse = client.runtime_statistics()
    if not m2eeresponse.has_error():
        stats.update(m2eeresponse.get_feedback())
    m2eeresponse = client.server_statistics()
    if not m2eeresponse.has_error():
        stats.update(m2eeresponse.get_feedback())
    if type(stats["requests"]) == list:
        # convert back to normal, whraagh
        bork = {}
        for x in stats["requests"]:
            bork[x["name"]] = x["value"]
        stats["requests"] = bork

    runtime_version = config.get_runtime_version()
    if runtime_version is not None and runtime_version >= 3.2:
        m2eeresponse = client.get_all_thread_stack_traces()
        if not m2eeresponse.has_error():
            stats["threads"] = len(m2eeresponse.get_feedback())

    java_version = guess_java_version(client, runtime_version, stats)
    return _populate_stats_by_java_version(stats, java_version), java_version


def _populate_stats_by_java_version(stats, java_version):
    """Populate stats according to the java version.

    The Mendix runtime uses the standard MemoryMXBean:
    The values from the `MemoryPoolMXBean`s go into the memorypool field and
    the values from the `MemoryMXBean` go into the init_, committed_, used_
    and max_ fields, both for the _heap and the nonheap memory.

    Since apparently in different Java versions these mean different things
    or are in different places, we need to shuffle these around depending
    on the Java version.

    """
    if "memorypools" in stats["memory"]:
        standardized_memory_pools = _standardize_memory_pools_output(
            stats["memory"]["memorypools"], java_version
        )
        stats["memory"].update(standardized_memory_pools)
        return stats
    elif java_version >= 8:
        # This branch should only be reached with a Mendix runtime version
        # <= 6.5 (i.e. before MemoryPools were added), and one using Java 8,
        # which seems to include all Mendix 6 runtimes
        memory = stats["memory"]
        metaspace = memory["eden"]
        eden = memory["tenured"]
        survivor = memory["permanent"]
        old = memory["used_heap"] - eden - survivor
        memory["permanent"] = metaspace
        memory["eden"] = eden
        memory["survivor"] = survivor
        memory["tenured"] = old
        return stats

    # Mendix 5.x runtimes are no longer supported.
    # So ideally we should never encounter a case where there are no
    # memorypools and java version less than 8.
    # However raise an exception, if we reach this point.
    raise RuntimeError("Java version less than 8 not supported.")


def _standardize_memory_pools_output(runtime_memory_pools, java_version):
    # type: (list[Mapping], int) -> Mapping[str, int]
    java_8_mapping = {
        "code": ("Code Cache",),
        "permanent": ("Metaspace",),
        "eden": ("Eden Space",),
        "survivor": ("Survivor Space",),
        "tenured": ("Tenured Gen",),
    }
    java_11_mapping = {
        "code": (
            "CodeHeap 'non-nmethods'",
            "CodeHeap 'profiled nmethods'",
            "CodeHeap 'non-profiled nmethods'",
        ),
        "permanent": ("Metaspace",),
        "eden": ("Eden Space",),
        "survivor": ("Survivor Space",),
        "tenured": ("Tenured Gen",),
    }

    if java_version == 8:
        pool_mapping = java_8_mapping
    elif java_version == 11:
        pool_mapping = java_11_mapping
    else:
        # Why raise, instead of trying and "guess" based on known JVM/JREs?
        # Because the mapping has changed in every supported JRE. Better to
        # fail fast, so that mapping can be confirmed during testing of a new
        # JVM/JRE version.
        raise NotImplementedError(
            "Java version {} does not yet have a memorypool mapping in "
            "m2ee tools".format(java_version)
        )

    # Transform memorypools from a list of dicts, to a dict of memory usages,
    # which is more what we want. Additionally ensure we use a standard pool
    # name. ie. For "PS Eden Space" use "Eden Space"
    memory_pools_dict = {
        _standard_pool_name(f["name"]): f["usage"]
        for f in runtime_memory_pools
    }

    output_stats = {}
    for our_memory_type, pool_names in pool_mapping.items():
        try:
            total = sum(
                [memory_pools_dict[pool_name] for pool_name in pool_names]
            )
        except KeyError as exc:
            got_fields = list(memory_pools_dict.keys())
            required_fields = list(itertools.chain(*pool_mapping.values()))
            logger.error(
                "Collecting JVM memory pool stats failed. Memory pool "
                "output did not match expected output. Needed: %s. Got: %s",
                required_fields,
                got_fields,
            )
            raise RuntimeError(
                "Unable to collect JVM memory pool stats. "
                "Please contact support!"
            ) from exc
        output_stats[our_memory_type] = total

    return output_stats


def _standard_pool_name(given_pool_name):
    """Return a standard memory pool name.

    The memory pool names could vary based on the garbage collector enabled.
    This function returns a standard name we could refer to.

    Available collectors :
    https://docs.oracle.com/en/java/javase/11/gctuning/available-collectors.html

    Here is an old gist listing the variations in the names:
    https://gist.github.com/szegedi/1474365

    """

    # mapping of standard memory pool name to all known names.
    pool_name_aliases = {
        "Eden Space": ("PS Eden Space", "Par Eden Space", "G1 Eden Space",),
        "Survivor Space": (
            "PS Survivor Space",
            "Par Survivor Space",
            "G1 Survivor Space",
        ),
        "Tenured Gen": ("PS Old Gen", "CMS Old Gen", "G1 Old Gen",),
    }

    for standard_name, valid_names in pool_name_aliases.items():
        for name in valid_names:
            if name == given_pool_name:
                return standard_name

    # If we can't find an alternative standard name,
    # just return the given memory pool name.
    return given_pool_name


def _populate_stats_by_java_version_old(stats, java_version):
    warnings.warn(
        "This calculation method is deprecated! Use "
        "m2ee.munin._populate_stats_by_java_version instead."
    )
    if "memorypools" in stats["memory"]:
        memorypools = stats["memory"]["memorypools"]
        if java_version == 7:
            # This branch should never be reached - according to
            # https://github.com/mendix/m2ee-tools/commit/95738d, MemoryPools
            # were only added some time after Mendix 6.5, but all versions of
            # Mendix 6 use Java 8.
            raise NotImplementedError("This branch should never be reached.")
            stats["memory"]["code"] = memorypools[0]["usage"]
            stats["memory"]["permanent"] = memorypools[4]["usage"]
            stats["memory"]["eden"] = memorypools[1]["usage"]
            stats["memory"]["survivor"] = memorypools[2]["usage"]
            stats["memory"]["tenured"] = memorypools[3]["usage"]
        else:
            stats["memory"]["code"] = memorypools[0]["usage"]
            # In previous versions of this code, the "Compressed Class Space"
            # pool at index 2 was erroneously used as "Permanent", when the
            # correct pool is the "Metaspace" pool at index 1.
            stats["memory"]["permanent"] = memorypools[1]["usage"]
            stats["memory"]["eden"] = memorypools[3]["usage"]
            stats["memory"]["survivor"] = memorypools[4]["usage"]
            stats["memory"]["tenured"] = memorypools[5]["usage"]
    elif java_version >= 8:
        # This branch should only be reached with a Mendix runtime version
        # <= 6.5 (i.e. before MemoryPools were added), and one using Java 8,
        # which seems to include all Mendix 6 runtimes, and some (but not all)
        # Mendix 5 runtimes.
        memory = stats["memory"]
        metaspace = memory["eden"]
        eden = memory["tenured"]
        survivor = memory["permanent"]
        old = memory["used_heap"] - eden - survivor
        memory["permanent"] = metaspace
        memory["eden"] = eden
        memory["survivor"] = survivor
        memory["tenured"] = old
    # Mendix 5 runtimes running on Java 7 already include the desired
    # statistics in the response from the runtime, so we don't need to do
    # anything.
    return stats


def write_last_known_good_stats_cache(stats, config_cache):
    logger.debug("Writing munin cache to %s" % config_cache)
    try:
        with open(config_cache, "w+") as f:
            f.write(json.dumps(stats))
    except Exception as e:
        logger.error(
            "Error writing munin config cache to %s: %s", config_cache, e
        )


def read_stats_from_last_known_good_stats_cache(config_cache):
    stats = None
    logger.debug("Loading munin cache from %s" % config_cache)
    try:
        fd = open(config_cache)
        stats = json.loads(fd.read())
        fd.close()
    except IOError as e:
        logger.error(
            "Error reading munin cache file %s: %s" % (config_cache, e)
        )
    except ValueError as e:
        logger.error(
            "Error parsing munin cache file %s: %s" % (config_cache, e)
        )
    return stats


def print_requests_config(name, stats):
    print("multigraph mxruntime_requests_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Requests per second")
    print("graph_title %s - MxRuntime Requests" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows the amount of requests this MxRuntime handles"
    )
    for sub in stats["requests"].keys():
        substrip = "_" + sub.strip("/").replace("-", "_")
        if sub != "":
            subname = sub
        else:
            subname = "/"
        print("%s.label %s" % (substrip, subname))
        print("%s.draw LINE1" % substrip)
        print(
            "%s.info amount of requests this MxRuntime handles on %s"
            % (substrip, subname)
        )
        print("%s.type DERIVE" % substrip)
        print("%s.min 0" % substrip)
    print("")


def print_requests_values(name, stats):
    print("multigraph mxruntime_requests_%s" % name)
    for sub, count in stats["requests"].items():
        substrip = "_" + sub.strip("/").replace("-", "_")
        print("%s.value %s" % (substrip, count))
    print("")


def print_connectionbus_config(name, stats):
    if "connectionbus" not in stats:
        return
    print("multigraph mxruntime_connectionbus_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Statements per second")
    print("graph_title %s - Database Queries" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows the amount of executed transactions and queries"
    )
    for s in stats["connectionbus"].keys():
        print("%s.label %ss" % (s, s))
        print("%s.draw LINE1" % s)
        print("%s.info amount of %ss" % (s, s))
        print("%s.type DERIVE" % s)
        print("%s.min 0" % s)
    print("")


def print_connectionbus_values(name, stats):
    if "connectionbus" not in stats:
        return
    print("multigraph mxruntime_connectionbus_%s" % name)
    for s, count in stats["connectionbus"].items():
        print("%s.value %s" % (s, count))
    print("")


def print_sessions_config(name, stats, graph_total_named_users):
    if type(stats["sessions"]) != dict:
        print_sessions_pre254_config(name, stats)
    else:
        print_sessions_since254_config(name, stats, graph_total_named_users)


def print_sessions_values(name, stats, graph_total_named_users):
    if type(stats["sessions"]) != dict:
        print_sessions_pre254_values(name, stats)
    else:
        print_sessions_since254_values(name, stats, graph_total_named_users)


def print_sessions_pre254_config(name, stats):
    """
    concurrent user sessions for mxruntime < 2.5.4
    named_user_sessions counts names as well as anonymous sessions
    !! you stil need to rename the rrd files in /var/lib/munin/ !!
    """
    print("multigraph mxruntime_sessions_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Concurrent user sessions")
    print("graph_title %s - MxRuntime Users" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the amount of concurrent user sessions")
    print("named_user_sessions.label concurrent user sessions")
    print("named_user_sessions.draw LINE1")
    print("named_user_sessions.info amount of concurrent user sessions")
    print("")


def print_sessions_pre254_values(name, stats):
    print("multigraph mxruntime_sessions_%s" % name)
    print("named_user_sessions.value %s" % stats["sessions"])
    print("")


def print_sessions_since254_config(name, stats, graph_total_named_users):
    print("multigraph mxruntime_sessions_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Concurrent user sessions")
    print("graph_title %s - MxRuntime Users" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows the amount of user accounts and sessions"
    )
    if graph_total_named_users:
        print("named_users.label named users")
        print("named_users.draw LINE1")
        print(
            "named_users.info total amount of named users in the application"
        )
    print("named_user_sessions.label concurrent named user sessions")
    print("named_user_sessions.draw LINE1")
    print("named_user_sessions.info amount of concurrent named user sessions")
    print("anonymous_sessions.label concurrent anonymous user sessions")
    print("anonymous_sessions.draw LINE1")
    print(
        "anonymous_sessions.info amount of concurrent anonymous user sessions"
    )
    print("")


def print_sessions_since254_values(name, stats, graph_total_named_users):
    print("multigraph mxruntime_sessions_%s" % name)
    if graph_total_named_users:
        print("named_users.value %s" % stats["sessions"]["named_users"])
    print(
        "named_user_sessions.value %s"
        % stats["sessions"]["named_user_sessions"]
    )
    print(
        "anonymous_sessions.value %s" % stats["sessions"]["anonymous_sessions"]
    )
    print("")


def print_jvmheap_config(name, stats):
    print("multigraph mxruntime_jvmheap_%s" % name)
    print("graph_args --base 1024 -l 0")
    print("graph_vlabel Bytes")
    print("graph_title %s - JVM Heap Memory Usage" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows memory pool information on the Java JVM"
    )
    print("tenured.label tenured generation")
    print("tenured.draw AREA")
    print(
        "tenured.info Old generation of the heap that holds long living objects"
    )
    print("tenured.colour COLOUR2")
    print("survivor.label survivor space")
    print("survivor.draw STACK")
    print("survivor.info Survivor Space of the Young Generation")
    print("survivor.colour COLOUR3")
    print("eden.label eden space")
    print("eden.draw STACK")
    print("eden.info Objects are created in Eden")
    print("eden.colour COLOUR4")
    print("free.label unused")
    print("free.draw STACK")
    print("free.info Unused memory reserved for use by the JVM heap")
    print("free.colour COLOUR5")
    print("limit.label heap size limit")
    print("limit.draw LINE1")
    print("limit.info Java Heap memory usage limit")
    print("limit.colour COLOUR6")
    print("")


def print_jvmheap_values(name, stats):
    print("multigraph mxruntime_jvmheap_%s" % name)
    memory = stats["memory"]
    for k in ["tenured", "survivor", "eden"]:
        print("%s.value %s" % (k, memory[k]))
    free = memory["max_heap"] - memory["used_heap"]
    print("free.value %s" % free)
    print("limit.value %s" % memory["max_heap"])
    print("")


def print_threadpool_config(name, stats):
    if "threadpool" not in stats:
        return
    print("multigraph m2eeserver_threadpool_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Jetty Threadpool")
    print("graph_title %s - Jetty Threadpool" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows threadpool usage information on Jetty")
    print("min_threads.label min threads")
    print("min_threads.draw LINE1")
    print("min_threads.info Minimum number of threads")
    print("max_threads.label max threads")
    print("max_threads.draw LINE1")
    print("max_threads.info Maximum number of threads")
    print("active_threads.label active threads")
    print("active_threads.draw LINE1")
    print("active_threads.info Active thread count")
    print("threadpool_size.label threadpool size")
    print("threadpool_size.draw LINE1")
    print("threadpool_size.info Current threadpool size")
    print("")


def print_threadpool_values(name, stats):
    if "threadpool" not in stats:
        return

    threadpool = stats["threadpool"]

    print("multigraph m2eeserver_threadpool_%s" % name)
    for k in [
        "min_threads",
        "max_threads",
        "active_threads",
        "threadpool_size",
    ]:
        print("%s.value %s" % (k, threadpool[k]))
    print("")


def print_cache_config(name, stats):
    if "cache" not in stats:
        return
    print("multigraph mxruntime_cache_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel objects")
    print("graph_title %s - Object Cache" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows the total amount of objects in the runtime object cache"
    )
    print("total.label Objects in cache")
    print("total.draw LINE1")
    print("total.info Total amount of objects")
    print("")


def print_cache_values(name, stats):
    if "cache" not in stats:
        return
    print("multigraph mxruntime_cache_%s" % name)
    print("total.value %s" % stats["cache"]["total_count"])
    print("")


def print_jvm_threads_config(name, stats):
    if "threads" not in stats:
        return
    print("multigraph mxruntime_threads_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel objects")
    print("graph_title %s - JVM Threads" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows the total amount of threads in the JVM process"
    )
    print("total.label threads")
    print("total.draw LINE1")
    print("total.info Total amount of threads in the JVM process")
    print("")


def print_jvm_threads_values(name, stats):
    if "threads" not in stats:
        return
    print("multigraph mxruntime_threads_%s" % name)
    print("total.value %s" % stats["threads"])
    print("")


def print_jvm_process_memory_config(name):
    if not smaps.has_smaps("self"):
        return
    print("multigraph mxruntime_jvm_process_memory_%s" % name)
    print("graph_args --base 1024 -l 0")
    print("graph_vlabel Bytes")
    print("graph_title %s - JVM Process Memory Usage" % name)
    print("graph_category Mendix")
    print(
        "graph_info This graph shows the total memory usage of the Java JVM process"
    )
    print("nativecode.label native code")
    print("nativecode.draw AREA")
    print("nativecode.info Native program code, e.g. the java binary itself")
    print("jar.label jar files")
    print("jar.draw STACK")
    print("jar.info JAR file contents loaded into memory")
    print("tenured.label tenured generation")
    print("tenured.draw STACK")
    print(
        "tenured.info Old generation of the Java Heap that holds long living objects"
    )
    print("survivor.label survivor space")
    print("survivor.draw STACK")
    print("survivor.info Survivor Space of the Young Generation, Java Heap")
    print("eden.label eden space")
    print("eden.draw STACK")
    print("eden.info Objects are created in Eden, Java Heap")
    print("javaheap.label unused java heap")
    print("javaheap.draw STACK")
    print("javaheap.info Unused Java Heap")
    print("permanent.label permanent generation")
    print("permanent.draw STACK")
    print(
        "permanent.info Non-heap memory used to store bytecode versions of classes"
    )
    print("codecache.label code cache")
    print("codecache.draw STACK")
    print(
        "codecache.info Non-heap memory used for compilation and storage of native code"
    )
    print("nativemem.label native memory")
    print("nativemem.draw STACK")
    print("nativemem.info Native heap and memory arenas")
    print("stacks.label thread stacks")
    print("stacks.draw STACK")
    print("stacks.info Thread stacks")
    print("other.label other")
    print("other.draw STACK")
    print("other.info Other, unknown, undetermined memory usage")
    print("total.label total")
    print("total.draw LINE1")
    print("total.info Total memory usage")
    print("")


def print_jvm_process_memory_values(name, stats, pid, client, java_version):
    if pid is None:
        return
    totals = smaps.get_smaps_rss_by_category(pid)
    if totals is None:
        return
    memory = stats["memory"]
    print("multigraph mxruntime_jvm_process_memory_%s" % name)

    for k in [
        "tenured",
        "survivor",
        "eden",
        "javaheap",
        "permanent",
        "nativemem",
        "stacks",
        "total",
        "jar",
        "nativecode",
        "code",
        "codecache",
    ]:
        print("%s.value %s" % (k, memory[k]))
    print("")


def augment_and_fix_stats(stats, pid, java_version):
    if pid is None:
        return
    totals = smaps.get_smaps_rss_by_category(pid)
    if totals is None:
        return
    memory = stats["memory"]
    memory["nativecode"] = totals[smaps.CATEGORY_CODE] * 1024
    memory["jar"] = totals[smaps.CATEGORY_JAR] * 1024

    nativemem = totals[smaps.CATEGORY_NATIVE_HEAP_ARENA] * 1024
    othermem = totals[smaps.CATEGORY_OTHER] * 1024
    javaheap_raw = totals[smaps.CATEGORY_JVM_HEAP] * 1024
    if java_version is not None and java_version >= 8:
        # Free unused heap space can be calculated
        # by subtracting used_heap from the committed_heap data
        # gathered from the Java MemoryMxBean interface.
        # https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryUsage.html
        # Previously, we were subtracting the used_heap from the
        # javaheap_raw value(calculated using the smaps file),
        # but it was resulting in negative unused javaheap metrics.
        javaheap = memory["committed_heap"] - memory["used_heap"]

        nativemem = nativemem + othermem
        othermem = 0
    else:
        # This branch should never be reached, as java
        # version less than 8 is no more supported.
        javaheap = (
            javaheap_raw
            - memory["used_heap"]
            - memory["code"]
            - memory["permanent"]
        )

    memory["javaheap"] = javaheap
    memory["codecache"] = memory["code"]
    memory["nativemem"] = nativemem
    memory["other"] = othermem
    memory["stacks"] = totals[smaps.CATEGORY_THREAD_STACK] * 1024
    memory["total"] = sum(totals.values()) * 1024

    threadpool = stats["threadpool"]
    threadpool_size = threadpool["threads"]
    threadpool["threadpool_size"] = threadpool_size
    idle_threads = threadpool["idle_threads"]
    threadpool["active_threads"] = threadpool_size - idle_threads

    return stats
