import json
import os
from unittest import TestCase
from unittest import mock

from buildpack.infrastructure import storage
from lib.m2ee.version import MXVersion


class TestCaseAzureBlobStoreDryRun(TestCase):

    azure_storage_vcap_example = """
{
        "objectstore": [
   {
    "binding_name": null,
    "credentials": {
     "account_name": "sapcp4f4f4f4f4f4f4f4f4f4f",
     "container_name": "sapcp-osaas-2d2d2d2d-cccc-4444-8888-4ed76dca688e",
     "container_uri": "https://sapcp4f81hh2hps11tx7iuc7.blob.core.windows.net/sapcp-osaas-2d2d2d2d-cccc-4444-8888-4ed76dca688e",
     "region": "westeurope",
     "sas_token": "sig=JC1hALu1%2FOFA%1FzyuCzuZKivlb%1IIYktBYxHKPF2OJz3U%3D\u0026sv=2017-01-17\u0026spr=https\u0026si=77777777-ffff-4444-bbbb-bdeafdd87d00\u0026sr=c"
    },
    "instance_name": "test-azure-nl_Test_XgXgX",
    "label": "objectstore",
    "name": "test-azure-nl_Test_XgXgX",
    "plan": "azure-standard",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "blobStore",
     "objectStore"
    ],
    "volume_mounts": []
   }
  ]
}
    """  # noqa

    @mock.patch(
        "buildpack.core.runtime.get_runtime_version",
        mock.MagicMock(return_value=MXVersion(7.13)),
    )
    def test_azure_blob_store(self):
        vcap = json.loads(self.azure_storage_vcap_example)
        os.environ["MENDIX_BLOBSTORE_TYPE"] = "azure"
        config = storage._get_azure_storage_specific_config(vcap)
        assert (
            config["com.mendix.storage.azure.Container"]
            == "sapcp-osaas-2d2d2d2d-cccc-4444-8888-4ed76dca688e"  # noqa
        )
        assert (
            config["com.mendix.storage.azure.SharedAccessSignature"]
            == "sig=JC1hALu1%2FOFA%1FzyuCzuZKivlb%1IIYktBYxHKPF2OJz3U%3D\u0026sv=2017-01-17\u0026spr=https\u0026si=77777777-ffff-4444-bbbb-bdeafdd87d00\u0026sr=c"  # noqa
        )
