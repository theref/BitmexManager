import pytest
from bitmex_manager import session


def test_initialise_clean():
    params = {'base_url': 'TestUrl',
              'api_key': 'ApiKey',
              'api_secret': 'ApiSecret',
              'order_id_prefix': 'IDPrefix'}
    session.initialise(**params)
    assert session.base_url == params['base_url']
    assert session.api_key == params['api_key']
    assert session.api_secret == params['api_secret']
    assert session.order_id_prefix == params['order_id_prefix']


def test_initialise_dirty():
    with pytest.raises(ValueError):
        session.initialise()


def test_build_https_session():
    assert 1 == 2


def test_build_websocket():
    assert 1 == 2