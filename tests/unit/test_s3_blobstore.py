import json
import os
from unittest import TestCase
from unittest import mock

from buildpack.infrastructure import storage
from lib.m2ee.version import MXVersion

S3_STORAGE_VCAP_EXAMPLE = """
{
  "amazon-s3": [
   {
    "binding_name": null,
    "credentials": {
     "access_key_id": "fake-access-key-from-vcap",
     "bucket": "fake-bucket-from-vcap",
     "endpoint": "fake-s3-endpoint-from-vcap",
     "key_prefix": "fake-key-prefix-from-vcap/",
     "key_suffix": "_fake-key-suffix-from-vcap",
     "secret_access_key": "fake-secret-access-key-from-vcap",
     "username": "fake-username-from-vcap",
     "warning": "don't use key_suffix, it is there for legacy reasons only"
    },
    "instance_name": "ops-432a659e.test.foo.io-storage",
    "label": "amazon-s3",
    "name": "ops-432a659e.test.foo.io-storage",
    "plan": "singlebucket",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "object-storage",
     "s3"
    ],
    "volume_mounts": []
   }
  ]
}
    """  # noqa

S3_TVM_STORAGE_VCAP_EXAMPLE = """
{
  "amazon-s3": [
   {
    "binding_name": null,
    "credentials": {
     "bucket": "fake-bucket-from-tvm-vcap",
     "endpoint": "fake-s3-endpoint-from-tvm-vcap",
     "key_prefix": "fake-key-prefix-from-tvm-vcap/",
     "tvm_endpoint": "tvm-endpoint.mendix.com",
     "tvm_password": "fake-password-from-tvm-vcap",
     "tvm_username": "fake-username-from-tvm-vcap"
    },
    "instance_name": "ops-432a659e.test.foo.io-storage",
    "label": "amazon-s3",
    "name": "ops-432a659e.test.foo.io-storage",
    "plan": "singlebucket",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "object-storage",
     "s3"
    ],
    "volume_mounts": []
   }
  ]
}
    """  # noqa


class TestCaseS3BlobStoreDryRun(TestCase):
    @mock.patch(
        "buildpack.core.runtime.get_runtime_version",
        mock.MagicMock(return_value=MXVersion(7.23)),
    )
    def test_s3_blobstore(self):
        vcap = json.loads(S3_STORAGE_VCAP_EXAMPLE)
        config = storage._get_s3_specific_config(vcap)
        assert (
            config["com.mendix.core.StorageService"] == "com.mendix.storage.s3"
        )
        assert (
            config["com.mendix.storage.s3.AccessKeyId"]
            == "fake-access-key-from-vcap"
        )
        assert (
            config["com.mendix.storage.s3.SecretAccessKey"]
            == "fake-secret-access-key-from-vcap"
        )
        assert (
            config["com.mendix.storage.s3.BucketName"]
            == "fake-key-prefix-from-vcap"
        )
        assert (
            config["com.mendix.storage.s3.EndPoint"]
            == "fake-s3-endpoint-from-vcap/fake-bucket-from-vcap"
        )

    @mock.patch(
        "buildpack.core.runtime.get_runtime_version",
        mock.MagicMock(return_value=MXVersion(7.23)),
    )
    @mock.patch(
        "buildpack.infrastructure.storage._get_credentials_from_tvm",
        mock.MagicMock(
            return_value=("fake-access-key", "fake-secret-access-key")
        ),
    )
    def test_s3_blobstore_tvm_runtime_without_sts(self):
        vcap = json.loads(S3_TVM_STORAGE_VCAP_EXAMPLE)
        config = storage._get_s3_specific_config(vcap)
        assert (
            config["com.mendix.core.StorageService"] == "com.mendix.storage.s3"
        )
        assert config["com.mendix.storage.s3.AccessKeyId"] == "fake-access-key"
        assert (
            config["com.mendix.storage.s3.SecretAccessKey"]
            == "fake-secret-access-key"
        )
        assert (
            config["com.mendix.storage.s3.BucketName"]
            == "fake-key-prefix-from-tvm-vcap"
        )
        assert (
            config["com.mendix.storage.s3.EndPoint"]
            == "fake-s3-endpoint-from-tvm-vcap/fake-bucket-from-tvm-vcap"
        )

    @mock.patch(
        "buildpack.core.runtime.get_runtime_version",
        mock.MagicMock(return_value=MXVersion(9.2)),
    )
    @mock.patch(
        "buildpack.infrastructure.storage._get_credentials_from_tvm",
        mock.MagicMock(
            return_value=("fake-access-key", "fake-secret-access-key")
        ),
    )
    def test_s3_blobstore_tvm_runtime_with_sts(self):
        vcap = json.loads(S3_TVM_STORAGE_VCAP_EXAMPLE)
        config = storage._get_s3_specific_config(vcap)
        assert (
            config["com.mendix.core.StorageService"] == "com.mendix.storage.s3"
        )
        assert (
            config["com.mendix.storage.s3.tokenService.Url"]
            == "https://tvm-endpoint.mendix.com/v1/gettoken"
        )
        assert (
            config["com.mendix.storage.s3.tokenService.Username"]
            == "fake-username-from-tvm-vcap"
        )
        assert (
            config["com.mendix.storage.s3.tokenService.Password"]
            == "fake-password-from-tvm-vcap"
        )
        assert (
            config["com.mendix.storage.s3.tokenService.RefreshPercentage"]
            == 80
        )
        assert (
            config["com.mendix.storage.s3.tokenService.RetryIntervalInSeconds"]
            == 10
        )
        assert (
            config["com.mendix.storage.s3.BucketName"]
            == "fake-key-prefix-from-tvm-vcap"
        )
        assert (
            config["com.mendix.storage.s3.EndPoint"]
            == "fake-s3-endpoint-from-tvm-vcap/fake-bucket-from-tvm-vcap"
        )

    """
    When environment variable CERTIFICATE_AUTHORITIES is set and the Mendix
    Runtime does support STS, IAM credentials must be used
    """

    @mock.patch(
        "buildpack.core.runtime.get_runtime_version",
        mock.MagicMock(return_value=MXVersion(9.2)),
    )
    @mock.patch(
        "buildpack.infrastructure.storage._get_credentials_from_tvm",
        mock.MagicMock(
            return_value=("fake-access-key", "fake-secret-access-key")
        ),
    )
    def test_s3_blobstore_tvm_runtime_with_sts_and_cas(self):
        vcap = json.loads(S3_TVM_STORAGE_VCAP_EXAMPLE)
        os.environ["CERTIFICATE_AUTHORITIES"] = "fake-certificate-authority"
        config = storage._get_s3_specific_config(vcap)
        assert (
            config["com.mendix.core.StorageService"] == "com.mendix.storage.s3"
        )
        assert config["com.mendix.storage.s3.AccessKeyId"] == "fake-access-key"
        assert (
            config["com.mendix.storage.s3.SecretAccessKey"]
            == "fake-secret-access-key"
        )
        assert (
            config["com.mendix.storage.s3.BucketName"]
            == "fake-key-prefix-from-tvm-vcap"
        )
        assert (
            config["com.mendix.storage.s3.EndPoint"]
            == "fake-s3-endpoint-from-tvm-vcap/fake-bucket-from-tvm-vcap"
        )
