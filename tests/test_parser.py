import pytest

from app.agent import parse_intent


@pytest.mark.parametrize("message, action, ticker, amount", [
    ("Buy $500 of AAPL", "BUY", "AAPL", 500),
    ("buy 500 dollars of msft", "BUY", "MSFT", 500),
    ("Buy $1,000 more of AAPL", "BUY", "AAPL", 1000),
    ("purchase $250.50 worth of GOOGL", "BUY", "GOOGL", 250.5),
    ("Sell $200 of AMZN", "SELL", "AMZN", 200),
])
def test_trade_commands(message, action, ticker, amount):
    intent = parse_intent(message)
    assert intent["action"] == action
    assert intent["ticker"] == ticker
    assert intent["amount"] == amount


def test_account_and_positions():
    assert parse_intent("show my account balance")["action"] == "ACCOUNT"
    assert parse_intent("list my holdings")["action"] == "POSITIONS"


def test_unknown():
    assert parse_intent("hello there")["action"] == "UNKNOWN"
