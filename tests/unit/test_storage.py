import os
from unittest import TestCase
from unittest import mock

from .test_s3_blobstore import S3_STORAGE_VCAP_EXAMPLE
from buildpack import util
from buildpack.infrastructure import storage
from lib.m2ee.version import MXVersion


class M2EEMock:
    class ConfigMock:
        def __init__(self):
            self._conf = {"mxruntime": {}}

    def __init__(self):
        self.config = self.ConfigMock()


def _upsert_core_storage_setting(m2ee, value="bar"):
    util.upsert_custom_runtime_setting(
        m2ee,
        storage.STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY,
        value,
        overwrite=True,
        append=False,
    )


def _upsert_custom_storage_setting(m2ee, key="foo", value="bar"):
    util.upsert_custom_runtime_setting(
        m2ee,
        storage.STORAGE_CUSTOM_RUNTIME_SETTINGS_PREFIX + key,
        value,
        overwrite=True,
        append=False,
    )


class TestCaseStorageOverride(TestCase):
    @mock.patch.dict(
        os.environ,
        {"VCAP_SERVICES": S3_STORAGE_VCAP_EXAMPLE},
        clear=True,
    )
    @mock.patch(
        "buildpack.core.runtime.get_runtime_version",
        mock.MagicMock(return_value=MXVersion(7.23)),
    )
    def _assert_storage_service_override(self, outcome, user_setting=True):
        m2ee = M2EEMock()
        if user_setting:
            _upsert_core_storage_setting(m2ee, value=outcome)

        storage.update_config(m2ee)
        assert (
            util.get_custom_runtime_setting(
                m2ee, storage.STORAGE_CORE_CUSTOM_RUNTIME_SETTINGS_KEY
            )
            == outcome
        )

    def test_override_settings(self):
        self._assert_storage_service_override("bar", user_setting=True)

    def test_do_not_override_settings(self):
        self._assert_storage_service_override(
            "com.mendix.storage.s3", user_setting=False
        )


class TestCaseDetectUserDefinedStorageSettings(TestCase):
    def test_detect_user_defined_settings_none(self):
        m2ee = M2EEMock()
        assert not storage._is_user_defined_config(m2ee)

    def test_detect_user_defined_settings_core_setting(self):
        m2ee = M2EEMock()
        _upsert_core_storage_setting(m2ee)
        assert storage._is_user_defined_config(m2ee)

    def test_detect_user_defined_settings_custom_setting(self):
        m2ee = M2EEMock()
        _upsert_custom_storage_setting(m2ee)
        assert storage._is_user_defined_config(m2ee)

    def test_detect_user_defined_settings_full_settings(self):
        m2ee = M2EEMock()
        _upsert_core_storage_setting(m2ee)
        _upsert_custom_storage_setting(m2ee)
        assert storage._is_user_defined_config(m2ee)
