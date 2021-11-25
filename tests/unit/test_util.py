import glob
import os
import tempfile
import unittest

from buildpack import util


class M2EEMock:
    class ConfigMock:
        def __init__(self):
            self._conf = {}

    def __init__(self):
        self.config = self.ConfigMock()


class TestUtil(unittest.TestCase):

    # Works with a set of similar filenames only
    def _test_delete_old_versions(
        self, prefix, versions, index_to_keep, indexes_to_remove
    ):
        temp_dir = tempfile.TemporaryDirectory()

        files = []
        for version in versions:
            files.append(
                os.path.join(temp_dir.name, "{}{}".format(prefix, version))
            )

        for f in files:
            open(f, "a").close()

        test_file = files[index_to_keep]

        util._delete_other_versions(temp_dir.name, os.path.basename(test_file))

        result = glob.glob("%s/*.*" % temp_dir.name)

        j = 0
        for i in indexes_to_remove:
            del files[i - j]
            j += 1

        temp_dir.cleanup()

        return set(result) == set(files)

    def test_delete_old_versions(self):

        # Example dependencies that we can expect:
        # - AdoptOpenJDK-jre-11.0.3-linux-x64.tar.gz
        # - mendix-8.4.1.63369.tar.gz
        # - nginx-1.15.10-linux-x64-cflinuxfs2-6247377a.tgz
        # - cf-datadog-sidecar-v0.21.2_master_103662.tar.gz

        openjdk_prefix = "AdoptOpenJDK-jre-"
        openjdk_versions = ["11.0.3-linux-x64.tar.gz"]

        assert self._test_delete_old_versions(
            openjdk_prefix, openjdk_versions, 0, {}
        )

        dd_prefix = "cf-datadog-sidecar-"
        dd_versions = [
            "v0.11.1_master_78318.tar.gz",
            "v0.21.1_master_98363.tar.gz",
            "v0.21.2_master_103662.zip",
        ]

        assert self._test_delete_old_versions(dd_prefix, dd_versions, 0, [1])

        mx_prefix = "mendix-"
        mx_versions = [
            "8.4.1.63369.tar.gz",
            "8.5.0.64176.tar.gz",
            "8.6.1.1701.tar.gz",
            "8.7.0.1476.tar.gz",
        ]

        assert self._test_delete_old_versions(
            mx_prefix, mx_versions, 1, [0, 2, 3]
        )

        ng_prefix = "nginx-"
        ng_versions = ["1.15.10-linux-x64-cflinuxfs2-6247377a.tgz"]

        assert self._test_delete_old_versions(ng_prefix, ng_versions, 0, {})

    def test_find_file_in_directory(self):
        temp_dir = tempfile.TemporaryDirectory()

        file_names = [
            "dependency1.zip",
            "a/dependency2.zip",
            "a/b/dependency3.zip",
            "dependency4.zip/dependency4.zip",
        ]
        files = [os.path.join(temp_dir.name, f) for f in file_names]
        for f in files:
            util.mkdir_p(os.path.dirname(f))
            open(f, "a").close()

        for f in file_names:
            result = util._find_file_in_directory(
                os.path.basename(f), temp_dir.name
            )
            assert (
                result
                and util.is_path_accessible(result)
                and os.path.isfile(result)
            )

        temp_dir.cleanup()

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
            util._upsert_m2ee_config_setting(
                m2ee, "SomeSection", "SomeKey", "value2"
            )

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
        m2ee.config._conf["m2ee"] = {
            "custom_environment": {"SOME_VAR": "SOME_VALUE"}
        }

        util.upsert_custom_environment_variable(
            m2ee, "ANOTHER_VAR", "ANOTHER_VALUE"
        )
        util.upsert_custom_environment_variable(
            m2ee, "SOME_VAR", "ANOTHER_VALUE"
        )

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
