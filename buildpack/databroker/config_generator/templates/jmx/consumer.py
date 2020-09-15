import os

jmx_metrics = [
    {
        "include": {
            "bean_regex": "kafka\.consumer:type=consumer-metrics,client-id=.*",
            "attribute": {
                "time-between-poll-avg": {
                    "alias": "kafka.consumer.time-between-poll-avg"
                },
                "time-between-poll-max": {
                    "alias": "kafka.consumer.time-between-poll-max"
                },
                "last-poll-seconds-ago": {
                    "alias": "kafka.consumer.last-poll-seconds-ago"
                },
                "poll-idle-ratio-avg": {
                    "alias": "kafka.consumer.poll-idle-ratio-avg"
                },
            },
        }
    },
    {
        "include": {
            "bean_regex": "kafka\.consumer:type=consumer-coordinator-metrics,client-id=.*",
            "attribute": {
                "commit-latency-avg": {
                    "alias": "kafka.consumer.coordinator.commit-latency-avg"
                },
                "commit-latency-max": {
                    "alias": "kafka.consumer.coordinator.commit-latency-max"
                },
                "commit-rate": {
                    "alias": "kafka.consumer.coordinator.commit-rate"
                },
                "commit-total": {
                    "alias": "kafka.consumer.coordinator.commit-total"
                },
                "assigned-partitions": {
                    "alias": "kafka.consumer.coordinator.assigned-partitions"
                },
                "heartbeat-response-time-max": {
                    "alias": "kafka.consumer.coordinator.heartbeat-response-time-max"
                },
                "heartbeat-rate": {
                    "alias": "kafka.consumer.coordinator.heartbeat-rate"
                },
                "heartbeat-total": {
                    "alias": "kafka.consumer.coordinator.heartbeat-total"
                },
                "join-time-avg": {
                    "alias": "kafka.consumer.coordinator.join-time-avg"
                },
                "join-time-max": {
                    "alias": "kafka.consumer.coordinator.join-time-max"
                },
                "join-rate": {"alias": "kafka.consumer.coordinator.join-rate"},
                "join-total": {
                    "alias": "kafka.consumer.coordinator.join-total"
                },
                "sync-time-avg": {
                    "alias": "kafka.consumer.coordinator.sync-time-avg"
                },
                "sync-time-max": {
                    "alias": "kafka.consumer.coordinator.sync-time-max"
                },
                "sync-rate": {"alias": "kafka.consumer.coordinator.sync-rate"},
                "sync-total": {
                    "alias": "kafka.consumer.coordinator.sync-total"
                },
                "rebalance-latency-avg": {
                    "alias": "kafka.consumer.coordinator.rebalance-latency-avg"
                },
                "rebalance-latency-max": {
                    "alias": "kafka.consumer.coordinator.rebalance-latency-max"
                },
                "rebalance-latency-total": {
                    "alias": "kafka.consumer.coordinator.rebalance-latency-total"
                },
                "rebalance-total": {
                    "alias": "kafka.consumer.coordinator.rebalance-total"
                },
                "rebalance-rate-per-hour": {
                    "alias": "kafka.consumer.coordinator.rebalance-rate-per-hour"
                },
                "failed-rebalance-total": {
                    "alias": "kafka.consumer.coordinator.failed-rebalance-total"
                },
                "failed-rebalance-rate-per-hour": {
                    "alias": "kafka.consumer.coordinator.failed-rebalance-rate-per-hour"
                },
                "last-rebalance-seconds-ago": {
                    "alias": "kafka.consumer.coordinator.last-rebalance-seconds-ago"
                },
                "last-heartbeat-seconds-ago": {
                    "alias": "kafka.consumer.coordinator.last-heartbeat-seconds-ago"
                },
                "partitions-revoked-latency-avg": {
                    "alias": "kafka.consumer.coordinator.partitions-revoked-latency-avg"
                },
                "partitions-revoked-latency-max": {
                    "alias": "kafka.consumer.coordinator.partitions-revoked-latency-max"
                },
                "partitions-assigned-latency-avg": {
                    "alias": "kafka.consumer.coordinator.partitions-assigned-latency-avg"
                },
                "partitions-assigned-latency-max": {
                    "alias": "kafka.consumer.coordinator.partitions-assigned-latency-max"
                },
                "partitions-lost-latency-avg": {
                    "alias": "kafka.consumer.coordinator.partitions-lost-latency-avg"
                },
                "partitions-lost-latency-max": {
                    "alias": "kafka.consumer.coordinator.partitions-lost-latency-max"
                },
            },
        }
    },
    {
        "include": {
            "bean_regex": "kafka\.consumer:type=consumer-fetch-manager-metrics,client-id=.*",
            "attribute": {
                "bytes-consumed-rate": {
                    "alias": "kafka.consumer.fetch.manager.bytes-consumed-rate"
                },
                "bytes-consumed-total": {
                    "alias": "kafka.consumer.fetch.manager.bytes-consumed-total"
                },
                "fetch-latency-avg": {
                    "alias": "kafka.consumer.fetch.manager.fetch-latency-avg"
                },
                "fetch-latency-max": {
                    "alias": "kafka.consumer.fetch.manager.fetch-latency-max"
                },
                "fetch-rate": {
                    "alias": "kafka.consumer.fetch.manager.fetch-rate"
                },
                "fetch-size-avg": {
                    "alias": "kafka.consumer.fetch.manager.fetch-size-avg"
                },
                "fetch-size-max": {
                    "alias": "kafka.consumer.fetch.manager.fetch-size-max"
                },
                "fetch-throttle-time-avg": {
                    "alias": "kafka.consumer.fetch.manager.fetch-throttle-time-avg"
                },
                "fetch-throttle-time-max": {
                    "alias": "kafka.consumer.fetch.manager.fetch-throttle-time-max"
                },
                "fetch-total": {
                    "alias": "kafka.consumer.fetch.manager.fetch-total"
                },
                "records-consumed-rate": {
                    "alias": "kafka.consumer.fetch.manager.records-consumed-rate"
                },
                "records-consumed-total": {
                    "alias": "kafka.consumer.fetch.manager.records-consumed-total"
                },
                "records-lag-max": {
                    "alias": "kafka.consumer.fetch.manager.records-lag-max"
                },
                "records-lead-min": {
                    "alias": "kafka.consumer.fetch.manager.records-lead-min"
                },
                "records-per-request-avg": {
                    "alias": "kafka.consumer.fetch.manager.records-per-request-avg"
                },
            },
        }
    },
    {
        "include": {
            "bean_regex": "kafka\.consumer:type=consumer-fetch-manager-metrics,client-id=.*,topic=.*",
            "attribute": {
                "bytes-consumed-rate": {
                    "alias": "kafka.consumer.fetch.manager.bytes-consumed-rate"
                },
                "bytes-consumed-total": {
                    "alias": "kafka.consumer.fetch.manager.bytes-consumed-total"
                },
                "fetch-size-avg": {
                    "alias": "kafka.consumer.fetch.manager.fetch-size-avg"
                },
                "fetch-size-max": {
                    "alias": "kafka.consumer.fetch.manager.fetch-size-max"
                },
                "records-consumed-rate": {
                    "alias": "kafka.consumer.fetch.manager.records-consumed-rate"
                },
                "records-consumed-total": {
                    "alias": "kafka.consumer.fetch.manager.records-consumed-total"
                },
                "records-per-request-avg": {
                    "alias": "kafka.consumer.fetch.manager.records-per-request-avg"
                },
            },
        }
    },
    {
        "include": {
            "bean_regex": "kafka\.consumer:type=consumer-fetch-manager-metrics,partition=.*,topic=.*,client-id=.*",
            "attribute": {
                "preferred-read-replica": {
                    "alias": "kafka.consumer.fetch.manager.preferred-read-replica"
                },
                "records-lag": {
                    "alias": "kafka.consumer.fetch.manager.records-lag"
                },
                "records-lag-avg": {
                    "alias": "kafka.consumer.fetch.manager.records-lag-avg"
                },
                "records-lag-max": {
                    "alias": "kafka.consumer.fetch.manager.records-lag-max"
                },
                "records-lead": {
                    "alias": "kafka.consumer.fetch.manager.records-lead"
                },
                "records-lead-avg": {
                    "alias": "kafka.consumer.fetch.manager.records-lead-avg"
                },
                "records-lead-min": {
                    "alias": "kafka.consumer.fetch.manager.records-lead-min"
                },
            },
        }
    },
    {
        "include": {
            "bean": "com.mendix:type=DataBroker",
            "attribute": {
                "EntitiesCreatedCount": {
                    "alias": "com.mendix.EntitiesCreatedCount"
                },
                "EntitiesUpdatedCount": {
                    "alias": "com.mendix.EntitiesUpdatedCount"
                },
                "EntitiesDeletedCount": {
                    "alias": "com.mendix.EntitiesDeletedCount"
                },
            },
        }
    },
]
