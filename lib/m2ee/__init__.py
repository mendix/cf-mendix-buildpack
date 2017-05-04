def monkeypatch_logging():
    # register trace logging possibility
    TRACE = 5
    logging.addLevelName(TRACE, 'TRACE')
    setattr(logging, 'TRACE', TRACE)

    def loggerClassTrace(self, msg, *args, **kwargs):
        if self.isEnabledFor(TRACE):
            self._log(TRACE, msg, args, **kwargs)

    setattr(logging.getLoggerClass(), 'trace', loggerClassTrace)

    def rootTrace(msg, *args, **kwargs):
        if logging.root.isEnabledFor(TRACE):
            logging.root._log(TRACE, msg, args, **kwargs)
    setattr(logging, 'trace', rootTrace)


import logging
if not hasattr(logging, 'trace'):
    monkeypatch_logging()

from core import M2EE  # noqa
import pgutil  # noqa
import nagios  # noqa
import munin  # noqa
import version  # noqa

__version__ = '7.0.1'
