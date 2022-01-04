import os
import unittest

from buildpack.databroker import business_events
from buildpack import util


class TestDataBrokerBusinessEvents(unittest.TestCase):
    server_url = "b-3.mendix.kafka.eu-west-1.amazonaws.com:9096,b-1.mendix.kafka.eu-west-1.amazonaws.com:9096,b-2.mendix.kafka.eu-west-1.amazonaws.com:9096"
    apply_limits = "true"
    password = "abc23e4ftas78"
    channel_name = "e3c890204da74768"
    username = "ZaUx5uboxqsCRrA"
    kafka_vcap = f"""
        {{
            "kafka-testfree": [
                {{
                    "binding_guid": "8ee827cd-d718-446c-b956-224845d7faf4",
                    "binding_name": null,
                    "credentials": {{
                        "ServerUrl": "{server_url}",
                        "ApplyLimits": "{apply_limits}",
                        "Password": "{password}",
                        "ChannelName": "{channel_name}",
                        "Username": "{username}"
                    }},
                    "instance_guid": "d1564e67-2aeb-4a78-ac7b-db0752de574e",
                    "instance_name": "3d8fbea3-3741-4a8b-8d9c-5cd189960459-data",
                    "label": "kafka-testfree",
                    "name": "3d8fbea3-3741-4a8b-8d9c-5cd189960459-data",
                    "plan": "shared-business-events-testfree",
                    "provider": null,
                    "syslog_drain_url": null,
                    "tags": [
                    "databroker",
                    "MSK",
                    "Kafka"
                    ],
                    "volume_mounts": []
                }}
            ]
        }}
    """

    kafka_vcap_with_null_creds = f"""
        {{
            "kafka-testfree": [
                {{
                    "binding_guid": "8ee827cd-d718-446c-b956-224845d7faf4",
                    "binding_name": null,
                    "credentials": null,
                    "instance_guid": "d1564e67-2aeb-4a78-ac7b-db0752de574e",
                    "instance_name": "3d8fbea3-3741-4a8b-8d9c-5cd189960459-data",
                    "label": "kafka-testfree",
                    "name": "3d8fbea3-3741-4a8b-8d9c-5cd189960459-data",
                    "plan": "shared-business-events-testfree",
                    "provider": null,
                    "syslog_drain_url": null,
                    "tags": [
                    "databroker",
                    "MSK",
                    "Kafka"
                    ],
                    "volume_mounts": []
                }}
            ]
        }}
    """

    def _verify_vcap_info(self):
        business_events_cfg = business_events._get_config(
            util.get_vcap_services_data()
        )
        prefix = business_events.CONSTANTS_PREFIX
        assert business_events_cfg[f"{prefix}.ServerUrl"] == self.server_url
        assert (
            business_events_cfg[f"{prefix}.ApplyLimits"] == self.apply_limits
        )
        assert business_events_cfg[f"{prefix}.Password"] == self.password
        assert (
            business_events_cfg[f"{prefix}.ChannelName"] == self.channel_name
        )
        assert business_events_cfg[f"{prefix}.Username"] == self.username

    def test_business_events_config_happy_flow(self):
        os.environ["VCAP_SERVICES"] = self.kafka_vcap
        self._verify_vcap_info()

    def test_business_events_config_with_empty_creds(self):
        os.environ["VCAP_SERVICES"] = self.kafka_vcap_with_null_creds
        # make sure any exceptions in the business events does not cause any errors
        business_events_cfg = business_events._get_config(
            util.get_vcap_services_data()
        )
