import sys
import requests
import logging
import daiquiri
from bitmex_manager.websocket_utils import get_ws_url


this = sys.modules[__name__]

this.base_url = None
this.api_key = None
this.api_secret = None
this.order_id_prefix = None
this.logger = None
this.session = None


def initialise(base_url=None, api_key=None, api_secret=None, order_id_prefix=None, log_level=logging.INFO):
    if api_key is None:
        raise ValueError("Please set an API key and Secret to get started. See " +
                         "https://github.com/BitMEX/sample-market-maker/#getting-started for more information."
                        )

    this.base_url = base_url
    this.api_key = api_key
    this.api_secret = api_secret
    this.order_id_prefix = order_id_prefix

    daiquiri.setup(level=log_level)

    this.logger = daiquiri.getLogger(__name__)


def build_https_session():
    this.session = requests.Session()
    # These headers are always sent
    this.session.headers.update({'user-agent': 'jamescampbell.org.uk'})
    this.session.headers.update({'content-type': 'application/json'})
    this.session.headers.update({'accept': 'application/json'})


def build_websocket(symbol):
    ws_url = get_ws_url(endpoint=this.base_url, symbol=symbol)
