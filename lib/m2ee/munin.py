#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import os
import string

from m2ee.log import logger
import smaps

# Use json if available. If not (python 2.5) we need to import the simplejson
# module instead, which has to be available.
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError, ie:
        logger.critical("Failed to import json as well as simplejson. If "
                        "using python 2.5, you need to provide the simplejson "
                        "module in your python library path.")
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
        "max_stop_time_s": 0
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
        "max_heap": 0
    },
    "sessions": {
        "named_users": 0,
        "anonymous_sessions": 0,
        "named_user_sessions": 0,
        "user_sessions": {}
    },
    "requests": {
        "": 0,
        "debugger/": 0,
        "ws/": 0,
        "xas/": 0,
        "ws-doc/": 0,
        "file": 0
    },
    "cache": {
        "total_count": 0,
        "disk_count": 0,
        "memory_count": 0
    },
    "jetty": {
        "max_idle_time_s": 0,
        "current_connections": 0,
        "max_connections": 0,
        "max_idle_time_s_low_resources": 0
    },
    "connectionbus": {
        "insert": 0,
        "transaction": 0,
        "update": 0,
        "select": 0,
        "delete": 0
    }
}


def print_config(m2ee, name):
    stats, java_version = get_stats('config', m2ee.client, m2ee.config)
    if stats is None:
        return
    options = m2ee.config.get_munin_options()

    print_requests_config(name, stats)
    print_connectionbus_config(name, stats)
    print_sessions_config(name, stats, options.get('graph_total_named_users', True))
    print_jvmheap_config(name, stats)
    print_threadpool_config(name, stats)
    print_cache_config(name, stats)
    print_jvm_threads_config(name, stats)
    print_jvm_process_memory_config(name)


def print_values(m2ee, name):
    stats, java_version = get_stats('values', m2ee.client, m2ee.config)
    if stats is None:
        return
    options = m2ee.config.get_munin_options()

    print_requests_values(name, stats)
    print_connectionbus_values(name, stats)
    print_sessions_values(name, stats, options.get('graph_total_named_users', True))
    print_jvmheap_values(name, stats)
    print_threadpool_values(name, stats)
    print_cache_values(name, stats)
    print_jvm_threads_values(name, stats)
    print_jvm_process_memory_values(name, stats, m2ee.runner.get_pid(), m2ee.client, java_version)


def guess_java_version(client, runtime_version, stats):
    m2eeresponse = client.about()
    if not m2eeresponse.has_error():
        about = m2eeresponse.get_feedback()
        if 'java_version' in about:
            java_version = about['java_version']
            java_major, java_minor, _ = java_version.split('.')
            return int(java_minor)
    if runtime_version // 6:
        return 8
    if runtime_version // 5:
        m = stats['memory']
        if m['used_nonheap'] - m['code'] - m['permanent'] == 0:
            return 7
        return 8
    return None


def get_stats(action, client, config):
    # place to store last known good statistics result to be used for munin
    # config when the app is down or b0rked
    options = config.get_munin_options()
    config_cache = options.get('config_cache',
                               os.path.join(config.get_default_dotm2ee_directory(),
                                            'munin-cache.json'))

    # TODO: even better error/exception handling
    stats = None
    java_version = None
    try:
        stats, java_version = get_stats_from_runtime(client, config)
        write_last_known_good_stats_cache(stats, config_cache)
    except Exception, e:
        if action == 'config':
            logger.debug("Error fetching runtime/server statstics: %s", e)
            stats = read_stats_from_last_known_good_stats_cache(config_cache)
            if stats is None:
                stats = default_stats
        else:
            # assume something bad happened, like
            # socket.error: [Errno 111] Connection refused
            logger.error("Error fetching runtime/server statstics: %s", e)
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
    if type(stats['requests']) == list:
        # convert back to normal, whraagh
        bork = {}
        for x in stats['requests']:
            bork[x['name']] = x['value']
        stats['requests'] = bork

    runtime_version = config.get_runtime_version()
    if runtime_version is not None and runtime_version >= 3.2:
        m2eeresponse = client.get_all_thread_stack_traces()
        if not m2eeresponse.has_error():
            stats['threads'] = len(m2eeresponse.get_feedback())

    java_version = guess_java_version(client, runtime_version, stats)
    if 'memorypools' in stats['memory']:
        memorypools = stats['memory']['memorypools']
        if java_version == 7:
            stats['memory']['code'] = memorypools[0]['usage']
            stats['memory']['permanent'] = memorypools[4]['usage']
            stats['memory']['eden'] = memorypools[1]['usage']
            stats['memory']['survivor'] = memorypools[2]['usage']
            stats['memory']['tenured'] = memorypools[3]['usage']
        else:
            stats['memory']['code'] = memorypools[0]['usage']
            stats['memory']['permanent'] = memorypools[2]['usage']
            stats['memory']['eden'] = memorypools[3]['usage']
            stats['memory']['survivor'] = memorypools[4]['usage']
            stats['memory']['tenured'] = memorypools[5]['usage']
    elif java_version >= 8:
        memory = stats['memory']
        metaspace = memory['eden']
        eden = memory['tenured']
        survivor = memory['permanent']
        old = memory['used_heap'] - eden - survivor
        memory['permanent'] = metaspace
        memory['eden'] = eden
        memory['survivor'] = survivor
        memory['tenured'] = old
    return stats, java_version


def write_last_known_good_stats_cache(stats, config_cache):
    logger.debug("Writing munin cache to %s" % config_cache)
    try:
        file(config_cache, 'w+').write(json.dumps(stats))
    except Exception, e:
        logger.error("Error writing munin config cache to %s: %s",
                     (config_cache, e))


def read_stats_from_last_known_good_stats_cache(config_cache):
    stats = None
    logger.debug("Loading munin cache from %s" % config_cache)
    try:
        fd = open(config_cache)
        stats = json.loads(fd.read())
        fd.close()
    except IOError, e:
        logger.error("Error reading munin cache file %s: %s" %
                     (config_cache, e))
    except ValueError, e:
        logger.error("Error parsing munin cache file %s: %s" %
                     (config_cache, e))
    return stats


def print_requests_config(name, stats):
    print("multigraph mxruntime_requests_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Requests per second")
    print("graph_title %s - MxRuntime Requests" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the amount of requests this MxRuntime handles")
    for sub in stats['requests'].iterkeys():
        substrip = '_' + string.strip(sub, '/').replace('-', '_')
        if sub != '':
            subname = sub
        else:
            subname = '/'
        print("%s.label %s" % (substrip, subname))
        print("%s.draw LINE1" % substrip)
        print("%s.info amount of requests this MxRuntime handles on %s" % (substrip, subname))
        print("%s.type DERIVE" % substrip)
        print("%s.min 0" % substrip)
    print("")


def print_requests_values(name, stats):
    print("multigraph mxruntime_requests_%s" % name)
    for sub, count in stats['requests'].iteritems():
        substrip = '_' + string.strip(sub, '/').replace('-', '_')
        print("%s.value %s" % (substrip, count))
    print("")


def print_connectionbus_config(name, stats):
    if 'connectionbus' not in stats:
        return
    print("multigraph mxruntime_connectionbus_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Statements per second")
    print("graph_title %s - Database Queries" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the amount of executed transactions and queries")
    for s in stats['connectionbus'].iterkeys():
        print("%s.label %ss" % (s, s))
        print("%s.draw LINE1" % s)
        print("%s.info amount of %ss" % (s, s))
        print("%s.type DERIVE" % s)
        print("%s.min 0" % s)
    print("")


def print_connectionbus_values(name, stats):
    if 'connectionbus' not in stats:
        return
    print("multigraph mxruntime_connectionbus_%s" % name)
    for s, count in stats['connectionbus'].iteritems():
        print("%s.value %s" % (s, count))
    print("")


def print_sessions_config(name, stats, graph_total_named_users):
    if type(stats['sessions']) != dict:
        print_sessions_pre254_config(name, stats)
    else:
        print_sessions_since254_config(name, stats, graph_total_named_users)


def print_sessions_values(name, stats, graph_total_named_users):
    if type(stats['sessions']) != dict:
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
    print("named_user_sessions.value %s" % stats['sessions'])
    print("")


def print_sessions_since254_config(name, stats, graph_total_named_users):
    print("multigraph mxruntime_sessions_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel Concurrent user sessions")
    print("graph_title %s - MxRuntime Users" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the amount of user accounts and sessions")
    if graph_total_named_users:
        print("named_users.label named users")
        print("named_users.draw LINE1")
        print("named_users.info total amount of named users in the application")
    print("named_user_sessions.label concurrent named user sessions")
    print("named_user_sessions.draw LINE1")
    print("named_user_sessions.info amount of concurrent named user sessions")
    print("anonymous_sessions.label concurrent anonymous user sessions")
    print("anonymous_sessions.draw LINE1")
    print("anonymous_sessions.info amount of concurrent anonymous user sessions")
    print("")


def print_sessions_since254_values(name, stats, graph_total_named_users):
    print("multigraph mxruntime_sessions_%s" % name)
    if graph_total_named_users:
        print("named_users.value %s" % stats['sessions']['named_users'])
    print("named_user_sessions.value %s" %
          stats['sessions']['named_user_sessions'])
    print("anonymous_sessions.value %s" %
          stats['sessions']['anonymous_sessions'])
    print("")


def print_jvmheap_config(name, stats):
    print("multigraph mxruntime_jvmheap_%s" % name)
    print("graph_args --base 1024 -l 0")
    print("graph_vlabel Bytes")
    print("graph_title %s - JVM Heap Memory Usage" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows memory pool information on the Java JVM")
    print("tenured.label tenured generation")
    print("tenured.draw AREA")
    print("tenured.info Old generation of the heap that holds long living objects")
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
    memory = stats['memory']
    for k in ['tenured', 'survivor', 'eden']:
        print('%s.value %s' % (k, memory[k]))
    free = (memory['max_heap'] - memory['used_heap'])
    print("free.value %s" % free)
    print("limit.value %s" % memory['max_heap'])
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

    min_threads = stats['threadpool']['min_threads']
    max_threads = stats['threadpool']['max_threads']
    threadpool_size = stats['threadpool']['threads']
    idle_threads = stats['threadpool']['idle_threads']
    active_threads = threadpool_size - idle_threads

    print("multigraph m2eeserver_threadpool_%s" % name)
    print("min_threads.value %s" % min_threads)
    print("max_threads.value %s" % max_threads)
    print("active_threads.value %s" % active_threads)
    print("threadpool_size.value %s" % threadpool_size)
    print("")


def print_cache_config(name, stats):
    if "cache" not in stats:
        return
    print("multigraph mxruntime_cache_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel objects")
    print("graph_title %s - Object Cache" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the total amount of objects in the runtime object cache")
    print("total.label Objects in cache")
    print("total.draw LINE1")
    print("total.info Total amount of objects")
    print("")


def print_cache_values(name, stats):
    if "cache" not in stats:
        return
    print("multigraph mxruntime_cache_%s" % name)
    print("total.value %s" % stats['cache']['total_count'])
    print("")


def print_jvm_threads_config(name, stats):
    if "threads" not in stats:
        return
    print("multigraph mxruntime_threads_%s" % name)
    print("graph_args --base 1000 -l 0")
    print("graph_vlabel objects")
    print("graph_title %s - JVM Threads" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the total amount of threads in the JVM process")
    print("total.label threads")
    print("total.draw LINE1")
    print("total.info Total amount of threads in the JVM process")
    print("")


def print_jvm_threads_values(name, stats):
    if "threads" not in stats:
        return
    print("multigraph mxruntime_threads_%s" % name)
    print("total.value %s" % stats['threads'])
    print("")


def print_jvm_process_memory_config(name):
    if not smaps.has_smaps('self'):
        return
    print("multigraph mxruntime_jvm_process_memory_%s" % name)
    print("graph_args --base 1024 -l 0")
    print("graph_vlabel Bytes")
    print("graph_title %s - JVM Process Memory Usage" % name)
    print("graph_category Mendix")
    print("graph_info This graph shows the total memory usage of the Java JVM process")
    print("nativecode.label native code")
    print("nativecode.draw AREA")
    print("nativecode.info Native program code, e.g. the java binary itself")
    print("jar.label jar files")
    print("jar.draw STACK")
    print("jar.info JAR file contents loaded into memory")
    print("tenured.label tenured generation")
    print("tenured.draw STACK")
    print("tenured.info Old generation of the Java Heap that holds long living objects")
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
    print("permanent.info Non-heap memory used to store bytecode versions of classes")
    print("codecache.label code cache")
    print("codecache.draw STACK")
    print("codecache.info Non-heap memory used for compilation and storage of native code")
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
    memory = stats['memory']
    print("multigraph mxruntime_jvm_process_memory_%s" % name)
    print("nativecode.value %s" % (totals[smaps.CATEGORY_CODE] * 1024))
    print("jar.value %s" % (totals[smaps.CATEGORY_JAR] * 1024))

    javaheap = totals[smaps.CATEGORY_JVM_HEAP] * 1024
    for k in ['tenured', 'survivor', 'eden']:
        print('%s.value %s' % (k, memory[k]))
    if java_version is not None and java_version >= 8:
        print("javaheap.value %s" % (javaheap - memory['used_heap'] - memory['code']))
    else:
        print("javaheap.value %s" %
              (javaheap - memory['used_heap'] - memory['code'] - memory['permanent']))

    nativemem = totals[smaps.CATEGORY_NATIVE_HEAP_ARENA] * 1024
    othermem = totals[smaps.CATEGORY_OTHER] * 1024
    print("permanent.value %s" % memory['permanent'])
    print("codecache.value %s" % memory['code'])
    if java_version is not None and java_version >= 8:
        print("nativemem.value %s" % (nativemem + othermem - memory['permanent']))
        print("other.value 0")
    else:
        print("nativemem.value %s" % nativemem)
        print("other.value %s" % othermem)

    print("stacks.value %s" % (totals[smaps.CATEGORY_THREAD_STACK] * 1024))
    print("total.value %s" % (sum(totals.values()) * 1024))
    print("")
