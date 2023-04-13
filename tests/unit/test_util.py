import unittest

from buildpack import util


class M2EEMock:
    class ConfigMock:
        def __init__(self):
            self._conf = {}

    def __init__(self):
        self.config = self.ConfigMock()


class TestUtil(unittest.TestCase):
    def _test_upsert_m2ee_config_equals(
        self,
        value1,
        value2,
        expected_value,
        append=False,
        overwrite=False,
        section="SomeSection",
        key="SomeKey",
    ):
        m2ee = M2EEMock()
        if value1:
            m2ee.config._conf[section] = {key: value1}
        else:
            m2ee.config._conf[section] = {}

        util._upsert_m2ee_config_setting(
            m2ee,
            section,
            key,
            value2,
            append=append,
            overwrite=overwrite,
        )
        assert m2ee.config._conf[section][key] == expected_value

    def test_upsert_m2ee_config_section_insert(self):
        self._test_upsert_m2ee_config_equals(None, "value", "value")

    def test_upsert_m2ee_config_section_overwrite(self):
        self._test_upsert_m2ee_config_equals(
            "value1", "value2", "value2", overwrite=True
        )

    def test_upsert_m2ee_config_append_string(self):
        self._test_upsert_m2ee_config_equals(
            "value1", "value2", "value1value2", append=True
        )

    def test_upsert_m2ee_config_append_int(self):
        self._test_upsert_m2ee_config_equals(1, 2, 3, append=True)

    def test_upsert_m2ee_config_append_dict_without_overwrite(self):
        self._test_upsert_m2ee_config_equals(
            {"key1": "value1", "key2": "value2"},
            {"key2": "value2a", "key3": "value3"},
            {"key1": "value1", "key2": "value2", "key3": "value3"},
            append=True,
        )

    def test_upsert_m2ee_config_append_dict_with_overwrite(self):
        self._test_upsert_m2ee_config_equals(
            {"key1": "value1", "key2": "value2"},
            {"key2": "value2a", "key3": "value3"},
            {"key1": "value1", "key2": "value2a", "key3": "value3"},
            overwrite=True,
            append=True,
        )

    def test_upsert_m2ee_config_append_list(self):
        self._test_upsert_m2ee_config_equals(
            [1, 2, 3, 4],
            [5, 6, 7, 8, 1],
            [1, 2, 3, 4, 5, 6, 7, 8, 1],
            append=True,
        )

    def test_upsert_m2ee_config_append_set(self):
        self._test_upsert_m2ee_config_equals(
            {1, 2, 3, 4},
            {5, 6, 7, 8, 1},
            {1, 2, 3, 4, 5, 6, 7, 8},
            append=True,
        )

    def test_upsert_m2ee_config_overwrite_existing(self):
        m2ee = M2EEMock()
        m2ee.config._conf["SomeSection"] = {"SomeKey": "value1"}

        with self.assertRaises(ValueError):
            util._upsert_m2ee_config_setting(m2ee, "SomeSection", "SomeKey", "value2")

    def test_upsert_m2ee_config_append_type_difference(self):
        m2ee = M2EEMock()
        m2ee.config._conf["SomeSection"] = {"SomeKey": "value1"}

        with self.assertRaises(ValueError):
            util._upsert_m2ee_config_setting(
                m2ee, "SomeSection", "SomeKey", 2, append=True
            )

    def test_upsert_javaopts_string(self):
        m2ee = M2EEMock()
        m2ee.config._conf["m2ee"] = {"javaopts": []}

        util.upsert_javaopts(m2ee, "-DSomeOption")
        assert util.get_javaopts(m2ee) == ["-DSomeOption"]

    def test_upsert_javaopts_list(self):
        m2ee = M2EEMock()
        m2ee.config._conf["m2ee"] = {"javaopts": ["-DSomeOption3"]}

        util.upsert_javaopts(m2ee, ["-DSomeOption1", "-DSomeOption2"])
        assert util.get_javaopts(m2ee) == [
            "-DSomeOption3",
            "-DSomeOption1",
            "-DSomeOption2",
        ]

    def test_upsert_custom_environment_vars(self):
        m2ee = M2EEMock()
        m2ee.config._conf["m2ee"] = {"custom_environment": {"SOME_VAR": "SOME_VALUE"}}

        util.upsert_custom_environment_variable(m2ee, "ANOTHER_VAR", "ANOTHER_VALUE")
        util.upsert_custom_environment_variable(m2ee, "SOME_VAR", "ANOTHER_VALUE")

        assert util.get_custom_environment_variables(m2ee) == {
            "SOME_VAR": "ANOTHER_VALUE",
            "ANOTHER_VAR": "ANOTHER_VALUE",
        }

    def test_upsert_logging_config_dict(self):
        m2ee = M2EEMock()
        m2ee.config._conf["logging"] = [{"type": "tcpjsonlines1"}]

        util.upsert_logging_config(m2ee, {"type": "tcpjsonlines2"})
        assert m2ee.config._conf["logging"] == [
            {"type": "tcpjsonlines1"},
            {"type": "tcpjsonlines2"},
        ]
