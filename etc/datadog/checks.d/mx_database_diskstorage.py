import os

try:
    from datadog_checks.base import AgentCheck
except ImportError:
    from checks import AgentCheck

__version__ = "1.0.0"


class DatabaseDiskStorageCheck(AgentCheck):
    def check(self, instance):
        if "DATABASE_DISKSTORAGE" in os.environ:
            try:
                self.gauge(
                    "mx.database.diskstorage_size",
                    float(os.environ["DATABASE_DISKSTORAGE"]),
                )
            except ValueError:
                pass
