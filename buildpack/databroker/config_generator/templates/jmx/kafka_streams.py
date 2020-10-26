import os

jmx_metrics = {
    "host": "localhost",
    "port": 11004,
    "java_bin_path": str(os.path.abspath(".local/bin/java")),
    "java_options": "-Xmx50m -Xms15m",
    "conf": [
        {
            "include": {
                "bean_regex": "kafka\.streams:type=stream-metrics,client-id=.*",
                "attribute": {"version": {"alias": "kafka.streams.version"},},
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.streams:type=stream-thread-metrics,thread-id=.*",
                "attribute": {
                    "commit-latency-avg": {
                        "alias": "kafka.streams.thread.commit-latency-avg"
                    },
                    "commit-latency-max": {
                        "alias": "kafka.streams.thread.commit-latency-max"
                    },
                    "poll-latency-avg": {
                        "alias": "kafka.streams.thread.poll-latency-avg"
                    },
                    "poll-latency-max": {
                        "alias": "kafka.streams.thread.poll-latency-max"
                    },
                    "process-latency-avg": {
                        "alias": "kafka.streams.thread.process-latency-avg"
                    },
                    "process-latency-max": {
                        "alias": "kafka.streams.thread.process-latency-max"
                    },
                    "punctuate-latency-avg": {
                        "alias": "kafka.streams.thread.punctuate-latency-avg"
                    },
                    "punctuate-latency-max": {
                        "alias": "kafka.streams.thread.punctuate-latency-max"
                    },
                    "commit-rate": {
                        "alias": "kafka.streams.thread.commit-rate"
                    },
                    "commit-total": {
                        "alias": "kafka.streams.thread.commit-total"
                    },
                    "poll-rate": {"alias": "kafka.streams.thread.poll-rate"},
                    "poll-total": {"alias": "kafka.streams.thread.poll-total"},
                    "process-rate": {
                        "alias": "kafka.streams.thread.process-rate"
                    },
                    "process-total": {
                        "alias": "kafka.streams.thread.process-total"
                    },
                    "punctuate-rate": {
                        "alias": "kafka.streams.thread.punctuate-rate"
                    },
                    "punctuate-total": {
                        "alias": "kafka.streams.thread.punctuate-total"
                    },
                    "task-created-rate": {
                        "alias": "kafka.streams.thread.task-created-rate"
                    },
                    "task-created-total": {
                        "alias": "kafka.streams.thread.task-created-total"
                    },
                    "task-closed-rate": {
                        "alias": "kafka.streams.thread.task-closed-rate"
                    },
                    "task-closed-total": {
                        "alias": "kafka.streams.thread.task-closed-total"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.streams:type=stream-task-metrics,thread-id=.*,task-id=.*",
                "attribute": {
                    "process-latency-avg": {
                        "alias": "kafka.streams.task.process-latency-avg"
                    },
                    "process-latency-max": {
                        "alias": "kafka.streams.task.process-latency-max"
                    },
                    "process-rate": {
                        "alias": "kafka.streams.task.process-rate"
                    },
                    "process-total": {
                        "alias": "kafka.streams.task.process-total"
                    },
                    "commit-latency-avg": {
                        "alias": "kafka.streams.task.commit-latency-avg"
                    },
                    "commit-latency-max": {
                        "alias": "kafka.streams.task.commit-latency-max"
                    },
                    "commit-rate": {"alias": "kafka.streams.task.commit-rate"},
                    "commit-total": {
                        "alias": "kafka.streams.task.commit-total"
                    },
                    "record-lateness-avg": {
                        "alias": "kafka.streams.task.record-lateness-avg"
                    },
                    "record-lateness-max": {
                        "alias": "kafka.streams.task.record-lateness-max"
                    },
                    "enforced-processing-rate": {
                        "alias": "kafka.streams.task.enforced-processing-rate"
                    },
                    "enforced-processing-total": {
                        "alias": "kafka.streams.task.enforced-processing-total"
                    },
                    "dropped-records-rate": {
                        "alias": "kafka.streams.task.dropped-records-rate"
                    },
                    "dropped-records-total": {
                        "alias": "kafka.streams.task.dropped-records-total"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.streams:type=stream-processor-node-metrics,thread-id=.*,task-id=.*,processor-node-id=.*",
                "attribute": {
                    "process-rate": {
                        "alias": "kafka.streams.processor.process-rate"
                    },
                    "process-total": {
                        "alias": "kafka.streams.processor.process-total"
                    },
                    "suppression-emit-rate": {
                        "alias": "kafka.streams.processor.suppression-emit-rate"
                    },
                    "suppression-emit-total": {
                        "alias": "kafka.streams.processor.suppression-emit-total"
                    },
                },
            }
        },
    ],
}
