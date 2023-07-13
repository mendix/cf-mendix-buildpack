import os
import unittest
from unittest import mock

from buildpack.databroker import business_events
from buildpack import util


class TestDataBrokerBusinessEvents(unittest.TestCase):
    server_url = "b-3.mendix.kafka.eu-west-1.amazonaws.com:9096,b-1.mendix.kafka.eu-west-1.amazonaws.com:9096,b-2.mendix.kafka.eu-west-1.amazonaws.com:9096"
    apply_limits = "true"
    password = "abc23e4ftas78"
    username = "ZaUx5uboxqsCRrA"
    client_config_token = "adsads45678idassdasdasdaafXK6q7R"
    client_config_url = "https://testconfig.mendix.com/client-configs/AEPbRQqHCb6"
    kafka_shared_vcap_free = f"""
        {{
            "kafka-testfree": [
                {{
                    "binding_guid": "8ee827cd-d718-446c-b956-224845d7faf4",
                    "binding_name": null,
                    "credentials": {{
                        "ServerUrl": "{server_url}",
                        "ApplyLimits": "{apply_limits}",
                        "Password": "{password}",
                        "UserName": "{username}",
                        "ClientConfigAuthToken": "{client_config_token}",
                        "ClientConfigUrl": "{client_config_url}"
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

    kafka_shared_vcap_licensed = f"""
        {{
            "kafka-testlicensed": [
                {{
                    "binding_guid": "8ee827cd-d718-446c-b956-224845d7faf4",
                    "binding_name": null,
                    "credentials": {{
                        "ServerUrl": "{server_url}",
                        "Password": "{password}",
                        "UserName": "{username}",
                        "ClientConfigAuthToken": "{client_config_token}",
                        "ClientConfigUrl": "{client_config_url}"
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

    kafka_shared_vcap_with_null_creds = """
        {
            "kafka-testfree": [
                {
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
                }
            ]
        }
    """

    expected_client_config = """
        {
            "version": "1.0.0",
            "allowedOverrides": [
                "EventNameEnvironmentMap"
            ],
            "publish": {
                "events": [
                {
                    "eventName": "OrderAccepted",
                    "channel": "169b7967830f400381d54196fffe879d",
                    "topic": "businessevents.169b7967830f400381d54196fffe879d.1307defb000a43b1a7b5b1258587d14b"
                }
                ]
            },
            "subscribe": {
                "clientConfig": {
                "consumerGroupIdPrefix": "1307defb-000a-43b1-a7b5-b1258587d14b"
                },
                "events": [
                {
                    "eventName": "OrderShipped",
                    "channel": "0779c0d0269349ee9a3728eb56106bae",
                    "partialTopic": "businessevents.0779c0d0269349ee9a3728eb56106bae"
                },
                {
                    "eventName": "InventoryUpdate",
                    "channel": "509d8fd738da49358a6fb0b0b108d8eb",
                    "partialTopic": "businessevents.509d8fd738da49358a6fb0b0b108d8eb"
                }
                ]
            }
        }
    """

    module_constants_with_metrics = {
        "BusinessEvents.ApplyLimits": "False",
        "BusinessEvents.ChannelName": "superchannel",
        "BusinessEvents.ClientConfiguration": expected_client_config,
        "BusinessEvents.Password": "itsasecret",
        "BusinessEvents.PublishedEventEnvironmentMap": "",
        "BusinessEvents.ServerUrl": "0.0.0.0:0000",
        "BusinessEvents.SummaryLogIntervalSeconds": 120,
        "BusinessEvents.TruststoreLocation": "",
        "BusinessEvents.TruststorePassword": "",
        "BusinessEvents.UserName": "awesomeuser",
        "BusinessEvents.EnableHeartbeat": "True",
        "BusinessEvents.GenerateMetrics": "True",
    }

    module_constants_without_metrics = {
        "BusinessEvents.ApplyLimits": "False",
        "BusinessEvents.ChannelName": "superchannel",
        "BusinessEvents.ClientConfiguration": expected_client_config,
        "BusinessEvents.Password": "itsasecret",
        "BusinessEvents.PublishedEventEnvironmentMap": "",
        "BusinessEvents.ServerUrl": "0.0.0.0:0000",
        "BusinessEvents.SummaryLogIntervalSeconds": 120,
        "BusinessEvents.TruststoreLocation": "",
        "BusinessEvents.TruststorePassword": "",
        "BusinessEvents.UserName": "awesomeuser",
    }

    def _verify_vcap_info(self, is_apply_limits_present=True):
        with mock.patch(
            "buildpack.databroker.business_events._get_client_config",
            mock.MagicMock(return_value=self.expected_client_config),
        ):
            business_events_cfg = business_events._get_config(
                util.get_vcap_services_data(),
                self.module_constants_with_metrics,
            )
        prefix = business_events.CONSTANTS_PREFIX

        assert business_events_cfg[f"{prefix}.ServerUrl"] == self.server_url
        assert business_events_cfg[f"{prefix}.Password"] == self.password
        assert business_events_cfg[f"{prefix}.UserName"] == self.username
        assert (
            business_events_cfg[f"{prefix}.ClientConfiguration"]
            == self.expected_client_config
        )
        if is_apply_limits_present:
            assert business_events_cfg[f"{prefix}.ApplyLimits"] == self.apply_limits

    def test_business_events_config_happy_flow_free(self):
        os.environ["VCAP_SERVICES"] = self.kafka_shared_vcap_free
        self._verify_vcap_info()

    def test_business_events_config_happy_flow_licensed(self):
        os.environ["VCAP_SERVICES"] = self.kafka_shared_vcap_licensed
        self._verify_vcap_info(is_apply_limits_present=False)

    def test_business_events_config_with_empty_creds(self):
        os.environ["VCAP_SERVICES"] = self.kafka_shared_vcap_with_null_creds
        # make sure any exceptions in the business events does not cause any errors
        business_events._get_config(
            util.get_vcap_services_data(), self.module_constants_with_metrics
        )

    def test_business_events_metrics_constants_config_free(self):
        be_config = {}
        os.environ["PROFILE"] = "free"
        business_events._configure_business_events_metrics(
            be_config, self.module_constants_with_metrics
        )
        assert be_config["BusinessEvents.GenerateMetrics"] == "false"
        assert be_config["BusinessEvents.EnableHeartbeat"] == "false"

    def test_business_events_metrics_constants_config(self):
        be_config = {}
        business_events._configure_business_events_metrics(
            be_config, self.module_constants_with_metrics
        )
        assert be_config["BusinessEvents.GenerateMetrics"] == "true"
        assert be_config["BusinessEvents.EnableHeartbeat"] == "true"

    def test_business_events_no_metrics_constants_config(self):
        be_config = {}
        business_events._configure_business_events_metrics(
            be_config, self.module_constants_without_metrics
        )
        assert "BusinessEvents.GenerateMetrics" not in be_config
        assert "BusinessEvents.EnableHeartbeat" not in be_config
