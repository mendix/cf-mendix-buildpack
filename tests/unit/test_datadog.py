import os
import json
import unittest

from buildpack import datadog


class TestCaseDatadogUtilFunctions(unittest.TestCase):
    def test_get_service(self):

        tags_cases = [
            (["app:testapp", "service:testservice"], "testservice"),
            (["app:testapp"], "testapp"),
            (["service:testservice"], "testservice"),
            ([], "app"),
        ]

        for (tags, outcome) in tags_cases:
            with self.subTest(tags=tags, outcome=outcome):
                os.environ["TAGS"] = json.dumps(tags)
                self.assertEqual(datadog.get_service(), outcome)
