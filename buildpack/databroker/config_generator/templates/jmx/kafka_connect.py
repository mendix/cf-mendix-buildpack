import os

jmx_metrics = {
    "host": "localhost",
    "port": 11003,
    "java_bin_path": str(os.path.abspath(".local/bin/java")),
    "java_options": "-Xmx50m -Xms15m",
    "conf": [
        {
            "include": {
                "bean": "kafka.connect:type=connect-worker-metrics",
                "attribute": {
                    "connector-count": {
                        "alias": "kafka.connect.worker.connector-count"
                    },
                    "connector-startup-attempts-total": {
                        "alias": "kafka.connect.worker.connector-startup-attempts-total"
                    },
                    "connector-startup-failure-percentage": {
                        "alias": "kafka.connect.worker.connector-startup-failure-percentage"
                    },
                    "connector-startup-failure-total": {
                        "alias": "kafka.connect.worker.connector-startup-failure-total"
                    },
                    "connector-startup-success-percentage": {
                        "alias": "kafka.connect.worker.connector-startup-success-percentage"
                    },
                    "connector-startup-success-total": {
                        "alias": "kafka.connect.worker.connector-startup-success-total"
                    },
                    "task-count": {"alias": "kafka.connect.worker.task-count"},
                    "task-startup-failure-percentage": {
                        "alias": "kafka.connect.worker.task-startup-failure-percentage"
                    },
                    "task-startup-failure-total": {
                        "alias": "kafka.connect.worker.task-startup-failure-total"
                    },
                    "task-startup-success-percentage": {
                        "alias": "kafka.connect.worker.task-startup-success-percentage"
                    },
                    "task-startup-success-total": {
                        "alias": "kafka.connect.worker.task-startup-success-total"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.connect:type=connect-worker-metrics,connector=.*",
                "attribute": {
                    "connector-destroyed-task-count": {
                        "alias": "kafka.connect.worker.connector-destroyed-task-count"
                    },
                    "connector-failed-task-count": {
                        "alias": "kafka.connect.worker.connector-failed-task-count"
                    },
                    "connector-paused-task-count": {
                        "alias": "kafka.connect.worker.connector-paused-task-count"
                    },
                    "connector-running-task-count": {
                        "alias": "kafka.connect.worker.connector-running-task-count"
                    },
                    "connector-total-task-count": {
                        "alias": "kafka.connect.worker.connector-total-task-count"
                    },
                    "connector-unassigned-task-count": {
                        "alias": "kafka.connect.worker.connector-unassigned-task-count"
                    },
                },
            }
        },
        {
            "include": {
                "bean": "kafka.connect:type=connect-worker-rebalance-metrics",
                "attribute": {
                    "completed-rebalances-total": {
                        "alias": "kafka.connect.worker.rebalance.completed-rebalances-total"
                    },
                    "connect-protocol": {
                        "alias": "kafka.connect.worker.rebalance.connect-protocol"
                    },
                    "epoch": {"alias": "kafka.connect.worker.rebalance.epoch"},
                    "leader-name": {
                        "alias": "kafka.connect.worker.rebalance.leader-name"
                    },
                    "rebalance-avg-time-ms": {
                        "alias": "kafka.connect.worker.rebalance.rebalance-avg-time-ms"
                    },
                    "rebalance-max-time-ms": {
                        "alias": "kafka.connect.worker.rebalance.rebalance-max-time-ms"
                    },
                    "rebalancing": {
                        "alias": "kafka.connect.worker.rebalance.rebalancing"
                    },
                    "time-since-last-rebalance-ms": {
                        "alias": "kafka.connect.worker.rebalance.time-since-last-rebalance-ms"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.connect:type=connector-metrics,connector=.*",
                "attribute": {
                    "connector-class": {
                        "alias": "kafka.connect.connector-class"
                    },
                    "connector-type": {
                        "alias": "kafka.connect.connector-type"
                    },
                    "connector-version": {
                        "alias": "kafka.connect.connector-version"
                    },
                    "status": {"alias": "kafka.connect.status"},
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.connect:type=connector-task-metrics,connector=.*,task=.*",
                "attribute": {
                    "batch-size-avg": {
                        "alias": "kafka.connect.task.batch-size-avg"
                    },
                    "batch-size-max": {
                        "alias": "kafka.connect.task.batch-size-max"
                    },
                    "offset-commit-avg-time-ms": {
                        "alias": "kafka.connect.task.offset-commit-avg-time-ms"
                    },
                    "offset-commit-failure-percentage": {
                        "alias": "kafka.connect.task.offset-commit-failure-percentage"
                    },
                    "offset-commit-max-time-ms": {
                        "alias": "kafka.connect.task.offset-commit-max-time-ms"
                    },
                    "offset-commit-success-percentage": {
                        "alias": "kafka.connect.task.offset-commit-success-percentage"
                    },
                    "pause-ratio": {"alias": "kafka.connect.task.pause-ratio"},
                    "running-ratio": {
                        "alias": "kafka.connect.task.running-ratio"
                    },
                    "status": {"alias": "kafka.connect.task.status"},
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.connect:type=source-task-metrics,connector=.*,task=.*",
                "attribute": {
                    "poll-batch-avg-time-ms": {
                        "alias": "kafka.connect.source.task.poll-batch-avg-time-ms"
                    },
                    "poll-batch-max-time-ms": {
                        "alias": "kafka.connect.source.task.poll-batch-max-time-ms"
                    },
                    "source-record-active-count": {
                        "alias": "kafka.connect.source.task.source-record-active-count"
                    },
                    "source-record-active-count-avg": {
                        "alias": "kafka.connect.source.task.source-record-active-count-avg"
                    },
                    "source-record-active-count-max": {
                        "alias": "kafka.connect.source.task.source-record-active-count-max"
                    },
                    "source-record-poll-rate": {
                        "alias": "kafka.connect.source.task.source-record-poll-rate"
                    },
                    "source-record-poll-total": {
                        "alias": "kafka.connect.source.task.source-record-poll-total"
                    },
                    "source-record-write-rate": {
                        "alias": "kafka.connect.source.task.source-record-write-rate"
                    },
                    "source-record-write-total": {
                        "alias": "kafka.connect.source.task.source-record-write-total"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "kafka\.connect:type=task-error-metrics,connector=.*,task=.*",
                "attribute": {
                    "deadletterqueue-produce-failures": {
                        "alias": "kafka.connect.task.error.deadletterqueue-produce-failures"
                    },
                    "deadletterqueue-produce-requests": {
                        "alias": "kafka.connect.task.error.deadletterqueue-produce-requests"
                    },
                    "last-error-timestamp": {
                        "alias": "kafka.connect.task.error.last-error-timestamp"
                    },
                    "total-errors-logged": {
                        "alias": "kafka.connect.task.error.total-errors-logged"
                    },
                    "total-record-errors": {
                        "alias": "kafka.connect.task.error.total-record-errors"
                    },
                    "total-record-failures": {
                        "alias": "kafka.connect.task.error.total-record-failures"
                    },
                    "total-records-skipped": {
                        "alias": "kafka.connect.task.error.total-records-skipped"
                    },
                    "total-retries": {
                        "alias": "kafka.connect.task.error.total-retries"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "debezium\.postgres:type=connector-metrics,context=snapshot,server=.*",
                "attribute": {
                    "LastEvent": {
                        "alias": "debezium.postgres.snapshot.last-event"
                    },
                    "MilliSecondsSinceLastEvent": {
                        "alias": "debezium.postgres.snapshot.milliseconds-since-last-event"
                    },
                    "TotalNumberOfEventsSeen": {
                        "alias": "debezium.postgres.snapshot.total-number-of-events-seen"
                    },
                    "NumberOfEventsFiltered": {
                        "alias": "debezium.postgres.snapshot.number-of-events-filtered"
                    },
                    "MonitoredTables": {
                        "alias": "debezium.postgres.snapshot.monitored-tables"
                    },
                    "QueueTotalCapacity": {
                        "alias": "debezium.postgres.snapshot.queue-total-capacity"
                    },
                    "QueueRemainingCapacity": {
                        "alias": "debezium.postgres.snapshot.queue-remaining-capacity"
                    },
                    "TotalTableCount": {
                        "alias": "debezium.postgres.snapshot.total-table-count"
                    },
                    "RemainingTableCount": {
                        "alias": "debezium.postgres.snapshot.remaining-table-count"
                    },
                    "SnapshotRunning": {
                        "alias": "debezium.postgres.snapshot.snapshot-running"
                    },
                    "SnapshotAborted": {
                        "alias": "debezium.postgres.snapshot.snapshot-aborted"
                    },
                    "SnapshotCompleted": {
                        "alias": "debezium.postgres.snapshot.snapshot-completed"
                    },
                    "SnapshotDurationInSeconds": {
                        "alias": "debezium.postgres.snapshot.snapshot-duration-in-seconds"
                    },
                    "RowsScanned": {
                        "alias": "debezium.postgres.snapshot.rows-scanned"
                    },
                },
            }
        },
        {
            "include": {
                "bean_regex": "debezium\.postgres:type=connector-metrics,context=streaming,server=.*",
                "attribute": {
                    "LastEvent": {
                        "alias": "debezium.postgres.streaming.last-event"
                    },
                    "MilliSecondsSinceLastEvent": {
                        "alias": "debezium.postgres.streaming.milliseconds-since-last-event"
                    },
                    "TotalNumberOfEventsSeen": {
                        "alias": "debezium.postgres.streaming.total-number-of-events-seen"
                    },
                    "NumberOfEventsFiltered": {
                        "alias": "debezium.postgres.streaming.number-of-events-filtered"
                    },
                    "MonitoredTables": {
                        "alias": "debezium.postgres.streaming.monitored-tables"
                    },
                    "QueueTotalCapacity": {
                        "alias": "debezium.postgres.streaming.queue-total-capacity"
                    },
                    "QueueRemainingCapacity": {
                        "alias": "debezium.postgres.streaming.queue-remaining-capacity"
                    },
                    "Connected": {
                        "alias": "debezium.postgres.streaming.connected"
                    },
                    "MilliSecondsBehindSource": {
                        "alias": "debezium.postgres.streaming.milliseconds-behind-source"
                    },
                    "NumberOfCommittedTransactions": {
                        "alias": "debezium.postgres.streaming.number-of-committed-transactions"
                    },
                    "SourceEventPosition": {
                        "alias": "debezium.postgres.streaming.source-event-position"
                    },
                    "LastTransactionId": {
                        "alias": "debezium.postgres.streaming.last-transaction-id"
                    },
                },
            }
        },
    ],
}
