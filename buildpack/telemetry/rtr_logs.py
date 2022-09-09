import asyncio
import base64
import json
import logging
import os
from datetime import datetime

from cloudfoundry_client.client import CloudFoundryClient

log = logging.getLogger(__name__)

# os.environ["ENDPOINT_BASE"] = ""
# os.environ["CLIENT_ID"] = ""
# os.environ["CLIENT_SECRET"] = ""
# os.environ["CUSTOM_CA"] = ""

APP_GUID = "3e23b1d5-69f3-4948-a687-9a6321544aaa"


async def get_logs():
    rlp_client = initialise_cf()
    async for line in get_logs_rlp(rlp_client, APP_GUID):
        # print(f'================ {line}')
        actual_message = base64.b64decode(line["log"]["payload"]).decode(
            "utf-8"
        )
        print(actual_message)
        log.error(f"test - ekrem - logline: {actual_message}")


async def get_logs_rlp(rlp_client, app_guid, expiry=None):  # noqa: C901
    """Consume log messages from RLP and parse them by batches,
    so that they can be processed futher by get_logs_for_app."""
    while True:
        if expiry and expiry < datetime.now():
            break
        try:
            stream = rlp_client.rlpgateway.stream_logs(
                app_guid, headers={"User-Agent": "MX-livelogging/test"}
            )
            async for message in stream:
                try:
                    formatted_message = (
                        message.decode("utf-8").strip("data:").strip("\n")
                    )
                    if formatted_message:
                        json_message = json.loads(formatted_message)
                        for batch in json_message["batch"]:
                            if "log" in batch.keys():
                                yield batch
                except json.decoder.JSONDecodeError:
                    log.info(f"SKIPPING: {message}")
        except (asyncio.CancelledError, asyncio.TimeoutError):
            log.info("Async request timeout.")


def initialise_cf():
    """Initialise CF and RLP gateway clients,
    create a URLVerifier instance."""

    rlp_client = CloudFoundryClient(
        target_endpoint=f'https://api.{os.getenv("ENDPOINT_BASE")}',
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        cert=os.getenv("SSL_CERT_FILE"),
    )
    rlp_client.init_with_client_credentials()

    return rlp_client


def setup_custom_ca_cert():
    """To get out custom SSL certificate working with urllib, we need to add a
    specific environment variable pointing to a specific file. This is nicer
    and more configurable than including the file in the actual app zip.
    """
    custom_ca_cert = os.getenv("CUSTOM_CA", "")
    with open("custom_ca.crt", "w") as ca_file:
        ca_file.write(custom_ca_cert)

    os.environ["SSL_CERT_FILE"] = "{}/custom_ca.crt".format(os.getcwd())


def main():
    setup_custom_ca_cert()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_logs())


if __name__ == '__main__':
    main()
