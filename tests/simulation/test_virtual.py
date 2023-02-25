from omspy.simulation.virtual import *
import pytest
import pendulum
import random
from unittest.mock import patch, Mock
from pydantic import ValidationError

random.seed(100)


@pytest.fixture
def basic_ticker():
    return Ticker(name="aapl", token=1234, initial_price=125)


@pytest.fixture
def basic_broker():
    tickers = [
        Ticker(name="aapl", token=1111, initial_price=100),
        Ticker(name="goog", token=2222, initial_price=125),
        Ticker(name="amzn", token=3333, initial_price=260),
    ]
    return VirtualBroker(tickers=tickers)


def test_generate_price():
    assert generate_price() == 102
    assert generate_price(1000, 2000) == 1470
    assert generate_price(110, 100) == 107


def test_generate_orderbook_default():
    ob = generate_orderbook()
    ob.bid[-1].price == 99.96
    ob.ask[-1].price == 100.04
    for b in ob.bid:
        assert 50 < b.quantity < 150
    for a in ob.ask:
        assert 50 < b.quantity < 150


def test_generate_orderbook_swap_bid_ask():
    ob = generate_orderbook(bid=100.05, ask=100)
    ob.bid[-1].price == 99.96
    ob.ask[-1].price == 100.04
    for b in ob.bid:
        assert 50 <= b.quantity <= 150
    for a in ob.ask:
        assert 50 <= b.quantity <= 150


def test_generate_orderbook_depth():
    ob = generate_orderbook(depth=100)
    ob.bid[-1].price == 99.01
    ob.ask[-1].price == 100.99
    assert len(ob.bid) == 100
    assert len(ob.ask) == 100


def test_generate_orderbook_price_and_tick_and_quantity():
    ob = generate_orderbook(bid=1000, ask=1005, tick=2, depth=10, quantity=600)
    ob.bid[-1].price == 982
    ob.ask[-1].price == 1023
    assert len(ob.bid) == len(ob.ask) == 10
    for b in ob.bid:
        assert 300 <= b.quantity <= 900
    for a in ob.ask:
        assert 300 <= b.quantity <= 900


def test_generate_orderbook_orders_count():
    with patch("random.randrange") as randrange:
        randrange.side_effect = [10, 10, 100, 100] * 20
        ob = generate_orderbook()
    for a, b in zip(ob.ask, ob.bid):
        assert a.orders_count <= a.quantity
        assert b.orders_count <= b.quantity


def test_ticker_defaults():
    ticker = Ticker(name="abcd")
    assert ticker.name == "abcd"
    assert ticker.token is None
    assert ticker.initial_price == 100
    assert ticker.mode == TickerMode.RANDOM


def test_ticker_changed(basic_ticker):
    ticker = basic_ticker
    assert ticker.name == "aapl"
    assert ticker.token == 1234
    assert ticker.initial_price == 125
    assert ticker.mode == TickerMode.RANDOM
    assert ticker._high == ticker._low == ticker._ltp == 125


def test_ticker_is_random():
    ticker = Ticker(name="abcd")
    assert ticker.is_random is True
    ticker.mode = TickerMode.MANUAL
    assert ticker.is_random is False


def test_ticker_ltp(basic_ticker):
    ticker = basic_ticker
    for i in range(15):
        ticker.ltp
    assert ticker._ltp == 120
    assert ticker._high == 125
    assert ticker._low == 116.95


def test_ticker_ohlc(basic_ticker):
    ticker = basic_ticker
    ticker.ohlc() == dict(open=125, high=125, low=125, close=125)
    for i in range(15):
        ticker.ltp
    ticker.ohlc() == dict(open=125, high=125, low=116.95, close=120)


def test_virtual_broker_defaults(basic_broker):
    b = basic_broker
    assert b.name == "VBroker"
    assert len(b.tickers) == 3
    assert b.failure_rate == 0.001


def test_virtual_broker_is_failure(basic_broker):
    b = basic_broker
    assert b.is_failure is False
    b.failure_rate = 1.0  # everything should fail now
    assert b.is_failure is True
    with pytest.raises(ValidationError):
        b.failure_rate = -1
    with pytest.raises(ValidationError):
        b.failure_rate = 2


def test_virtual_broker_order_place_success(basic_broker):
    b = basic_broker
    known = pendulum.datetime(2023, 2, 1, 10, 17)
    with pendulum.test(known):
        response = b.order_place(symbol="aapl", quantity=10, side=1)
        assert response.status == "success"
        assert response.timestamp == known
        assert response.data.order_id is not None
    assert len(b._orders) == 1


def test_virtual_broker_order_place_success_fields(basic_broker):
    b = basic_broker
    known = pendulum.datetime(2023, 2, 1, 10, 17)
    with pendulum.test(known):
        response = b.order_place(
            symbol="aapl", quantity=10, side=1, price=100, trigger_price=99
        )
        d = response.data
        assert response.status == "success"
        assert response.timestamp == known
        assert response.data.order_id is not None
        assert d.price == 100
        assert d.trigger_price == 99
        assert d.symbol == "aapl"
        assert d.quantity == 10
        assert d.side == Side.BUY
        assert d.filled_quantity == 0
        assert d.canceled_quantity == 0
        assert d.pending_quantity == 10
        assert d.status == Status.OPEN


def test_virtual_broker_order_place_failure(basic_broker):
    b = basic_broker
    b.failure_rate = 1.0
    known = pendulum.datetime(2023, 2, 1, 10, 17)
    with pendulum.test(known):
        response = b.order_place(symbol="aapl", quantity=10, side=1, price=100)
        assert response.status == "failure"
        assert response.timestamp == known
        assert response.data is None


def test_virtual_broker_order_place_user_response(basic_broker):
    b = basic_broker
    b.failure_rate = 1.0
    response = b.order_place(response=dict(symbol="aapl", price=100))
    assert response == {"symbol": "aapl", "price": 100}


def test_virtual_broker_order_place_validation_error(basic_broker):
    b = basic_broker
    known = pendulum.datetime(2023, 2, 1, 10, 17)
    with pendulum.test(known):
        response = b.order_place()
        assert response.status == "failure"
        assert response.timestamp == known
        assert response.error_msg.startswith("Found 3 validation")
        assert response.data is None

        response = b.order_place(symbol="aapl", side=-1)
        assert response.status == "failure"
        assert response.timestamp == known
        assert response.error_msg.startswith("Found 1 validation")
        assert "quantity" in response.error_msg
        assert response.data is None

        response = b.order_place(symbol="aapl", quantity=100, side="buy")
        assert response.status == "failure"
        assert response.timestamp == known
        assert response.error_msg.startswith("Found 1 validation")
        assert "side" in response.error_msg
        assert response.data is None


def test_virtual_broker_get(basic_broker):
    b = basic_broker
    for i in (50, 100, 130):
        b.order_place(symbol="dow", side=1, quantity=i)
    assert len(b._orders) == 3
    order_id = list(b._orders.keys())[1]
    assert b.get(order_id) == list(b._orders.values())[1]


def test_virtual_broker_order_modify(basic_broker):
    b = basic_broker
    order = b.order_place(symbol="dow", side=1, quantity=50)
    order_id = order.data.order_id
    resp = b.order_modify(order_id, quantity=25)
    assert resp.status == "success"
    assert resp.data.quantity == 25
    resp = b.order_modify(order_id, price=1000)
    assert resp.status == "success"
    assert resp.data.price == 1000
    assert list(b._orders.values())[0].price == 1000


def test_virtual_broker_order_modify_failure(basic_broker):
    b = basic_broker
    order = b.order_place(symbol="dow", side=1, quantity=50)
    order_id = order.data.order_id
    resp = b.order_modify("hexid", quantity=25)
    assert resp.status == "failure"
    assert resp.data is None
    b.failure_rate = 1.0
    resp = b.order_modify(order_id, price=100)
    assert resp.status == "failure"
    assert resp.data is None


def test_virtual_broker_order_modify_kwargs_response(basic_broker):
    b = basic_broker
    resp = b.order_modify("hexid", quantity=25, response=dict(a=10, b=15))
    assert resp == dict(a=10, b=15)


def test_virtual_broker_order_cancel(basic_broker):
    b = basic_broker
    order = b.order_place(symbol="dow", side=1, quantity=50)
    order_id = order.data.order_id
    resp = b.order_cancel(order_id)
    assert resp.status == "success"
    assert resp.data.canceled_quantity == 50
    assert resp.data.filled_quantity == 0
    assert resp.data.pending_quantity == 0
    assert resp.data.status == Status.CANCELED


def test_virtual_broker_order_cancel_failure(basic_broker):
    b = basic_broker
    order = b.order_place(symbol="dow", side=1, quantity=50)
    order_id = order.data.order_id
    resp = b.order_modify("hexid", quantity=25)
    assert resp.status == "failure"
    assert resp.data is None
    order = b.get(order_id)
    order.filled_quantity = 50
    assert resp.status == "failure"


def test_virtual_broker_order_cancel_kwargs_response(basic_broker):
    b = basic_broker
    resp = b.order_cancel("hexid", quantity=25, response=dict(a=10, b=15))
    assert resp == dict(a=10, b=15)


def test_fake_broker_ltp():
    b = FakeBroker()
    random.seed(1000)
    assert b.ltp("aapl") == {"aapl": 106}
    random.seed(1000)
    assert b.ltp("aapl", end=150) == {"aapl": 149}
    random.seed(1000)
    assert b.ltp("goog", start=1000, end=1200) == {"goog": 1199}


def test_fake_broker_orderbook():
    b = FakeBroker()
    ob = b.orderbook("aapl")
    assert "aapl" in ob
    assert list(ob["aapl"].keys()) == ["bid", "ask"]
    assert len(ob["aapl"]["ask"]) == 5

    ob = b.orderbook("goog", bid=400, ask=405, depth=10, tick=1)
    assert len(ob["goog"]["bid"]) == 10
    assert ob["goog"]["bid"][-1]["price"] == 391
    assert ob["goog"]["ask"][-1]["price"] == 414


def test_generate_ohlc_default():
    random.seed(1001)
    ohlc = generate_ohlc()
    assert ohlc.open == 100
    assert ohlc.high == 103
    assert ohlc.low == 100
    assert ohlc.close == 102
    assert ohlc.last_price == 101
    assert ohlc.volume == 17876


def test_generate_ohlc_custom():
    random.seed(1002)
    ohlc = generate_ohlc(300, 380, 2e6)
    assert ohlc.open == 372
    assert ohlc.high == 376
    assert ohlc.low == 366
    assert ohlc.close == 369
    assert ohlc.last_price == 368
    assert ohlc.volume == 1546673


def test_fake_broker_ohlc():
    b = FakeBroker()
    random.seed(1001)
    quote = b.ohlc("goog")
    ohlc = quote["goog"]
    assert ohlc["open"] == 100
    assert ohlc["last_price"] == 101
    assert ohlc["volume"] == 17876

    random.seed(1001)
    quote = b.ohlc("aapl", start=400, end=450, volume=45000)
    ohlc = quote["aapl"]
    assert ohlc["high"] == 448
    assert ohlc["low"] == 403
    assert ohlc["last_price"] == 438
    assert ohlc["volume"] == 71954
