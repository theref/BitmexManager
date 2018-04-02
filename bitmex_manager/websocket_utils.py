import websocket
import threading
import ssl
import sys
import hmac
import traceback
import json
import daiquiri
from hashlib import sha256
from time import time, sleep
from urllib.parse import urlparse, urlunparse

this = sys.modules[__name__]
this.logger = daiquiri.getLogger(__name__)
this.error = None
this.ws = None
this.data = {}
this.keys = {}
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
                                     on_message=on_message,
                                     on_close=on_close,
                                     on_open=on_open,
                                     on_error=on_error,
                                     header=get_auth(api_key, api_secret)
                                     )

    wst = threading.Thread(target=lambda: this.ws.run_forever(sslopt=ssl_opt_ca_certs))
    wst.daemon = True

    this.logger.info("Connecting to %s" % ws_url)
    wst.start()

    # Wait for connect before continuing
    conn_timeout = 5
    while (not this.ws.sock or not this.ws.sock.connected) and conn_timeout and not this.error:
        sleep(1)
        conn_timeout -= 1

    if not conn_timeout or this.error:
        this.logger.error("Couldn't connect to WS! Exiting.")
        disconnect(this.ws)
        sys.exit(1)


def find_item_by_keys(keys, table, match_data):
    for item in table:
        matched = True
        for key in keys:
            if item[key] != match_data[key]:
                matched = False
        if matched:
            return item


def on_message(ws, msg):
    """Handler for parsing WS messages."""
    message = json.loads(msg)
    this.logger.debug(json.dumps(message))

    table = message['table'] if 'table' in message else None
    action = message['action'] if 'action' in message else None
    try:
        if 'subscribe' in message:
            if message['success']:
                this.logger.debug("Subscribed to %s." % message['subscribe'])
            else:
                this.error("Unable to subscribe to %s. Error: \"%s\" Please check and restart." %
                           (message['request']['args'][0], message['error']))
        elif 'status' in message:
            if message['status'] == 400:
                this.error(message['error'])
            if message['status'] == 401:
                this.error("API Key incorrect, please check and restart.")
        elif action:

            if table not in this.data:
                this.data[table] = []

            if table not in this.keys:
                this.keys[table] = []

            # There are four possible actions from the WS:
            # 'partial' - full table image
            # 'insert'  - new row
            # 'update'  - update row
            # 'delete'  - delete row
            if action == 'partial':
                this.logger.debug("%s: partial" % table)
                this.data[table] += message['data']
                # Keys are communicated on partials to let you know how to uniquely identify
                # an item. We use it for updates.
                this.keys[table] = message['keys']
            elif action == 'insert':
                this.logger.debug('%s: inserting %s' % (table, message['data']))
                this.data[table] += message['data']

                # Limit the max length of the table to avoid excessive memory usage.
                # Don't trim orders because we'll lose valuable state if we do.
                if table not in ['order', 'orderBookL2'] and len(this.data[table]) > MAX_TABLE_LEN:
                    this.data[table] = this.data[table][(MAX_TABLE_LEN // 2):]

            elif action == 'update':
                this.logger.debug('%s: updating %s' % (table, message['data']))
                # Locate the item in the collection and update it.
                for update_data in message['data']:
                    item = find_item_by_keys(this.keys[table], this.data[table], update_data)
                    if not item:
                        continue  # No item found to update. Could happen before push

                    # Log executions
                    if table == 'order':
                        is_canceled = 'ordStatus' in update_data and update_data['ordStatus'] == 'Canceled'
                        if 'cumQty' in update_data and not is_canceled:
                            cont_executed = update_data['cumQty'] - item['cumQty']
                            if cont_executed > 0:
                                instrument = this.get_instrument(item['symbol'])
                                this.logger.info("Execution: %s %d Contracts of %s at %.*f" %
                                                 (item['side'], cont_executed, item['symbol'],
                                                  instrument['tickLog'], item['price']))

                    # Update this item.
                    item.update(update_data)

                    # Remove canceled / filled orders
                    if table == 'order' and item['leavesQty'] <= 0:
                        this.data[table].remove(item)

            elif action == 'delete':
                this.logger.debug('%s: deleting %s' % (table, message['data']))
                # Locate the item in the collection and remove it.
                for deleteData in message['data']:
                    item = find_item_by_keys(this.keys[table], this.data[table], deleteData)
                    this.data[table].remove(item)
            else:
                raise Exception("Unknown action: %s" % action)
    except:
        this.logger.error(traceback.format_exc())


def on_open(ws):
    this.logger.debug("Websocket Opened.")


def on_close(ws):
    this.logger.info('Websocket Closed')
    disconnect(ws)


def on_error(ws, error):
    this.error = error
    disconnect(ws)


def get_auth(api_key, api_secret):
    """Return auth headers. Will use API Keys if present in settings."""
    this.logger.info("Authenticating with API Key.")
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
