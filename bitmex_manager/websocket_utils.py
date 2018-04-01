import websocket
import threading
import ssl
import sys
import hmac
from hashlib import sha256
from time import time, sleep
from urllib.parse import urlparse, urlunparse

this = sys.modules[__name__]

this.error = None
this.ws = None
this.data = None
MAX_TABLE_LEN = 200


def get_ws_url(endpoint=None, symbol=None):
    """Connect to the websocket and initialize data stores."""

    subscriptions = [sub + ':' + symbol for sub in ["quote", "trade"]]
    subscriptions += ["instrument"]
    subscriptions += [sub + ':' + symbol for sub in ["order", "execution"]]
    subscriptions += ["margin", "position"]

    url_parts = list(urlparse(endpoint))
    url_parts[0] = url_parts[0].replace('http', 'ws')
    url_parts[2] = "/realtime?subscribe=" + ",".join(subscriptions)
    ws_url = urlunparse(url_parts)

    return ws_url


def ws_connect(ws_url, api_key, api_secret):
    """Connect to the websocket in a thread."""

    ssl_defaults = ssl.get_default_verify_paths()
    ssl_opt_ca_certs = {'ca_certs': ssl_defaults.cafile}
    this.ws = websocket.WebSocketApp(ws_url,
                                     on_message=__on_message,
                                     on_close=on_close,
                                     on_open=on_open,
                                     on_error=on_error,
                                     header=get_auth(api_key, api_secret)
                                     )

    wst = threading.Thread(target=lambda: this.ws.run_forever(sslopt=ssl_opt_ca_certs))
    wst.daemon = True
    wst.start()

    # Wait for connect before continuing
    conn_timeout = 5
    while (not this.ws.sock or not this.ws.sock.connected) and conn_timeout and not this.error:
        sleep(1)
        conn_timeout -= 1

    if not conn_timeout or this.error:
        disconnect(this.ws)
        sys.exit(1)


def on_open():
    pass


def on_close():
    disconnect()


def on_error(error):
    this.error = error
    disconnect(this.ws)


def get_auth(api_key, api_secret):
    """Return auth headers. Will use API Keys if present in settings."""
    nonce = generate_nonce()
    return ["api-nonce: " + str(nonce),
            "api-signature: " + generate_signature(api_secret, 'GET', '/realtime', nonce, ''),
            "api-key:" + api_key
            ]


def generate_nonce():
    return int(round(time() * 1000))


def generate_signature(api_secret, verb, url, nonce, data):
    """Generate a request signature compatible with BitMEX.
    Parse the url so we can remove the base and extract just the path.
    Generates an API signature.
    A signature is HMAC_SHA256(secret, verb + path + nonce + data), hex encoded.
    Verb must be uppercased, url is relative, nonce must be an increasing 64-bit integer
    and the data, if present, must be JSON without whitespace between keys.

    For example, in psuedocode (and in real code below):

    verb=POST
    url=/api/v1/order
    nonce=1416993995705
    data={"symbol":"XBTZ14","quantity":1,"price":395.01}
    signature = HEX(HMAC_SHA256(secret, 'POST/api/v1/order1416993995705{"symbol":"XBTZ14","quantity":1,"price":395.01}'))
    """

    parsed_url = urlparse(url)
    path = parsed_url.path
    if parsed_url.query:
        path = path + '?' + parsed_url.query

    if isinstance(data, (bytes, bytearray)):
        data = data.decode('utf8')

    message = verb + path + str(nonce) + data
    signature = hmac.new(bytes(api_secret, 'utf8'), bytes(message, 'utf8'), digestmod=sha256).hexdigest()
    return signature


def disconnect(ws):
    ws.close()
