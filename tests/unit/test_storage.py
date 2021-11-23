import os
from unittest import TestCase
from unittest import mock

from .test_s3_blobstore import S3_STORAGE_VCAP_EXAMPLE
from buildpack import util
from buildpack.infrastructure import storage
from lib.m2ee.version import MXVersion


class M2EEMock:
    class ConfigMock:
        _conf = {"mxruntime": {}}

    config = ConfigMock()


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
        STORAGE_SERVICE_KEY = "com.mendix.core.StorageService"
        m2ee = M2EEMock()
        if user_setting:
            util.upsert_custom_runtime_setting(
                m2ee,
                STORAGE_SERVICE_KEY,
                outcome,
                overwrite=True,
                append=False,
            )

        storage.update_config(m2ee)
        assert (
            util.get_custom_runtime_setting(m2ee, STORAGE_SERVICE_KEY)
            == outcome
        )

    def test_override_settings(self):
        self._assert_storage_service_override("com.mendix.storage.foo")

    def test_do_not_override_settings(self):
        self._assert_storage_service_override(
            "com.mendix.storage.s3", user_setting=False
        )
