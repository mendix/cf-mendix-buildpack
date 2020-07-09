#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
# http://www.mendix.com/
#

import datetime

from .log import logger
from .profileutildp import format_dict_table

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


class Log:
    def __init__(self, request_id, data):
        self.__dict__.update(data)
        self.request_id = request_id
        self.action = json.loads(data["request_content"])["action"]
        self.queries = data["database_queries"]
        if hasattr(self, "start_time"):
            self.end_time_formatted = datetime.datetime.fromtimestamp(
                (self.start_time + self.duration)  # pylint: disable=no-member
                // 1000
            )
            self.start_time_formatted = datetime.datetime.fromtimestamp(
                self.start_time // 1000  # pylint: disable=no-member
            )

    def __str__(self):
        return self.pretty_format(True)

    def pretty_format(self, print_queries=True):
        if print_queries:
            queries = "\n\n".join(
                [
                    "query: %s \nduration:%s" % (x["query"], x["duration"])
                    for x in self.queries
                ]
            )
        elif not print_queries:
            queries = "Omitting, %s queries in total" % len(self.queries)
        elif len(self.queries) == 0:
            queries = " None"

        if hasattr(self, "user_roles"):
            userroles = ",".join(self.user_roles)  # pylint: disable=no-member
        else:
            userroles = None

        if hasattr(self, "form_name"):
            form_name = self.form_name  # pylint: disable=no-member
        else:
            form_name = None

        return (
            " \
Database queries: %s \n\n \
RequestId: %s \n \
Username: %s \n \
Userroles: %s \n \
Still running: %s \n \
Action: %s \n \
Start: %s \n \
End: %s \n \
Duration: %sms \n \
Form: %s \n \
Original request: %s \n\n \
"
            % (
                queries,
                self.request_id,
                self.username,  # pylint: disable=no-member
                userroles,
                self.still_running,  # pylint: disable=no-member
                self.action,
                self.start_time_formatted,
                self.end_time_formatted,
                self.duration,  # pylint: disable=no-member
                form_name,
                self.request_content,  # pylint: disable=no-member
            )
        )


def sort_logs(logs):
    logs = list(map(Log, list(logs.keys()), list(logs.values())))
    logs.sort(lambda x, y: y.duration - x.duration)

    return [x.__dict__ for x in logs]  # back to dict for printing method


def print_logs(logs):
    if len(logs) is 0:
        print("no logs found")
        return

    ordered_logs = sort_logs(logs)
    i = 0
    for o in ordered_logs:
        del o["request_content"]  # don't want to print that crap
        o[""] = i
        i = i + 1

    columns = len(ordered_logs[0])
    width = 1280

    column_names_in_order = [
        "",
        "action",
        "duration",
        "start_time_formatted",
        "end_time_formatted",
        "username",
        "still_running",
    ]
    print(
        format_dict_table(
            ordered_logs[:50],
            max_column_width=width / columns + 200,
            column_names=column_names_in_order,
        )
    )


def print_log(logs, request_nr, should_print_queries=True):
    if len(logs) < request_nr:
        print("Can't find request matching id %s" % request_nr)
        print("it might have already been flushed to the logs...")
        return
    log = Log(logs[request_nr]["request_id"], logs[request_nr])
    print(log.pretty_format(should_print_queries))


def to_csv(logs):
    print(format_as_csv(logs))


def format_as_csv(logs):
    if len(logs) == 0:
        return "no logs found"

    ordered_logs = sort_logs(logs)
    return "\n".join(["\t".join(map(str, x.values())) for x in ordered_logs])
