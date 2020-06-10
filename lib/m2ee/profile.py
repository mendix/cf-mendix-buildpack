#!/usr/bin/python
#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import cmd
import datetime
import sys

from .client import M2EEClient
from .profileutil import (
    print_logs,
    print_log,
    sort_logs,
    to_csv,
    format_as_csv,
)


class M2EEProfiler(cmd.Cmd):
    def __init__(self, m2ee_client):
        cmd.Cmd.__init__(self)
        self.m2ee_client = m2ee_client
        self.prompt = "\nAvailable commands: \
 \n start \t\t(starts profiler server-side)\t\
 \n stop \t\t(stops profiler server-side) \
 \n clear \t\t(flushes all requests to the logs)\
 \n get \t\t(retrieve and display all current requests)\
 \n xxxx \t\t(where xxxx is a requestid. add -nodb flag to omit queries) \
 \n csv \t\t(dumps to csv onscreen) \
 \n b \t\t(back)\
 \n> "

    def do_start(self, args):
        minimum_duration_to_log = self.get_minimum_duration(args.split())
        flush_interval = self.get_flush_interval(args.split())

        self.last_args = "%s %s" % (minimum_duration_to_log, flush_interval)
        response = self.m2ee_client.start_profiler(
            minimum_duration_to_log, flush_interval
        )
        if response is not None:
            self.print_response(response.get_feedback())

    def do_stop(self, args):
        response = self.m2ee_client.stop_profiler()
        if response is not None:
            self.print_response(response.get_feedback())

    def do_clear(self, args):
        self.do_stop(None)
        if hasattr(self, "last_args"):
            self.do_start(self.last_args)
        else:
            self.do_start("1000 30")

    def do_b(self, args):
        return True

    def do_exit(self, args):
        return True

    def do_EOF(self, args):
        print()
        return True

    def emptyline(self):
        pass

    def do_get(self, args=None):
        response = self.m2ee_client.get_profiler_logs()
        if response is not None:
            print_logs(response.get_feedback())
            self.logs_cache = response.get_feedback()

    def do_csv(self, args):
        response = self.m2ee_client.get_profiler_logs()
        if response is not None:
            to_csv(response.get_feedback())

    def do_cache(self, args=None):
        if hasattr(self, "logs_cache"):
            print_logs(self.logs_cache)
        else:
            print("no logs cached at this moment")

    def default(self, args=None):
        arglist = args.split()
        should_print_queries = len(arglist) == 1 or not arglist[1] == "-nodb"

        if not hasattr(self, "logs_cache"):
            print(
                "haven't retrieved any logs yet, can't show you anything "
                "with id %s" % args
            )
            return

        try:
            sorted_logs = sort_logs(self.logs_cache)
            nr = int(args[0])
            if nr < 0 or nr > (len(sorted_logs) - 1):
                raise ValueError
            print_log(sorted_logs, nr, should_print_queries)
        except ValueError:
            print("must provide a number between 0 and %s" % len(sorted_logs))

    def get_minimum_duration(self, args):
        minimum_duration_to_log = None
        if len(args) > 0:
            try:
                minimum_duration_to_log = int(args[0])
            except ValueError:
                pass

        while minimum_duration_to_log is None:
            try:
                answer = input(
                    "Minimum duration to log? Defaults to " "1000(ms) "
                )
                if answer == "":
                    minimum_duration_to_log = 1000
                else:
                    minimum_duration_to_log = int(answer)
            except ValueError:
                print("Valid integer needed")

        return minimum_duration_to_log

    def get_flush_interval(self, args):
        flush_interval = None
        if len(args) > 1:
            try:
                flush_interval = int(args[1])
            except ValueError:
                pass

        while flush_interval is None:
            try:
                answer = input("Flush interval? Defaults to 30 min ")
                if answer == "":
                    flush_interval = 30
                else:
                    flush_interval = int(answer)
            except ValueError:
                print("Valid integer needed")

        return flush_interval

    def print_response(self, json):
        if "message" in json:
            print(json["message"])
        else:
            print(json)


if __name__ == "__main__":
    server = "http://agile:8090"
    client = M2EEClient(server, "1")
    profiler = M2EEProfiler(client)

    if not client.ping():
        print("can't reach (or ping) server '%s', exiting..." % server)
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == "-csv":
        filename = "profile_%s.log" % str(datetime.datetime.now())
        if len(sys.argv) > 2:
            filename = sys.argv[2]

        out = open(filename, "w")
        out.write(
            format_as_csv(
                profiler.m2ee_client.get_profiler_logs().get_feedback()
            )
        )
        out.close()
    else:
        profiler.cmdloop()
