import json
import buildpack.runtime_components.storage as storage
import buildpack.runtime_components.security as security
import os
from unittest.mock import Mock


class M2EEConfigStub:
    def __init__(self, version):
        self.version = version

    def get_runtime_version(self):
        return self.version


class M2EEStub:
    def __init__(self, version):
        self.config = M2EEConfigStub(version)


class TestCaseS3BlobStoreDryRun:

    s3_storage_vcap_example = """
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

    s3_tvm_storage_vcap_example = """
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

    def test_s3_blobstore(self):
        vcap = json.loads(self.s3_storage_vcap_example)
        m2ee = M2EEStub(7.23)
        config = storage._get_s3_specific_config(vcap, m2ee)
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

    def test_s3_blobstore_tvm_runtime_without_sts(self):
        vcap = json.loads(self.s3_tvm_storage_vcap_example)
        m2ee = M2EEStub(7.23)
        storage._get_credentials_from_tvm = Mock(
            return_value=("fake-access-key", "fake-secret-access-key")
        )
        config = storage._get_s3_specific_config(vcap, m2ee)
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

    def test_s3_blobstore_tvm_runtime_with_sts(self):
        vcap = json.loads(self.s3_tvm_storage_vcap_example)
        m2ee = M2EEStub(9.2)
        config = storage._get_s3_specific_config(vcap, m2ee)
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

    def test_s3_blobstore_tvm_runtime_with_sts_and_cas(self):
        vcap = json.loads(self.s3_tvm_storage_vcap_example)
        m2ee = M2EEStub(9.2)
        storage._get_credentials_from_tvm = Mock(
            return_value=("fake-access-key", "fake-secret-access-key")
        )
        os.environ["CERTIFICATE_AUTHORITIES"] = "fake-certificate-authority"
        config = storage._get_s3_specific_config(vcap, m2ee)
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
