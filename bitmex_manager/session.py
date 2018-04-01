import sys

this = sys.modules[__name__]

this.base_url = None
this.api_key = None
this.api_secret = None
this.order_id_prefix = None


def initialise(base_url=None, api_key=None, api_secret=None, order_id_prefix=None):
    if api_key is None:
        raise ValueError("Please set an API key and Secret to get started. See " +
                         "https://github.com/BitMEX/sample-market-maker/#getting-started for more information."
                        )

    this.base_url = base_url
    this.api_key = api_key
    this.api_secret = api_secret
    this.order_id_prefix = order_id_prefix


def build_https_session():
    pass


def build_websocket():
    pass