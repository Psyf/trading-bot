from binance.um_futures import UMFutures as Client

client = Client(
    key="4f91993110b2a841eea762324914d503832a526815398ac0721da61e239500a6",
    secret="7ad9c14f64200f8e459ad5ae4700a6f7fe894f4a30f8f32356adcdf4fc237ec0",
    base_url="https://testnet.binancefuture.com",
)

account_balance = float(
    [b["availableBalance"] for b in client.account()["assets"] if b["asset"] == "USDT"][
        0
    ]
)
print(account_balance)

limit_order = {
    "symbol": "TRXUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "quantity": 10000,
    "reduceOnly": "false",
    "price": 0.0549,
    "timeInForce": "GTC",
}

sl = {
    "symbol": "TRXUSDT",
    "side": "SELL",
    "type": "STOP",
    "quantity": 10000,
    "reduceOnly": "true",
    "price": 0.05470,
    "stopPrice": 0.05470,
    "timeInForce": "GTE_GTC",
    "workingType": "MARK_PRICE",
}

tp = {
    "symbol": "TRXUSDT",
    "side": "SELL",
    "type": "TAKE_PROFIT",
    "quantity": 10000,
    "reduceOnly": "true",
    "stopPrice": 0.056,
    "price": 0.056,
    "timeInForce": "GTE_GTC",
    "workingType": "MARK_PRICE",
}

x = client.new_order(**limit_order)
print(x)
x = client.new_order(**sl)
print(x)
x = client.new_order(**tp)
print(x)

account_balance = float(
    [b["availableBalance"] for b in client.account()["assets"] if b["asset"] == "USDT"][
        0
    ]
)
print(account_balance)
