## How to run 
1. Setup Pyenv+Poetry on a local venv and `poetry install`
2. Fill up `.env` with the necessary environment variables 
3. Run telegram_bot.py so you can start syncing the messages in the group "Over99PercentWins". You need to be join the group beforehand. 
4. Run future_bot.py so it can start trading. We recommend trying on the futures testnet first for some time to see if everything is going according to plan. 
5. To reset, kill the scripts above and delete sqlite db (a local file) AND clear your futures positions on binance. Important to do both, else will fuck up. 

## Expected Value

We know the following:

1. stop loss at -8% and they cancel around 1.5% of calls
2. targets and their hit rates are at 0.5% (77%), 1.3% (74%), 2.1% (68%), 3.5% (57%), 4.3% (52%), 5.2% (47%)

If we set target at target 3, but it never reaches target 3, we'll sell it after a set period of time (say 24H) at market rate (which is > 92% of price paid)
But we don't know what that market rate is. This makes it difficult to calculate an EV without backtesting.

Simplistic model 1 -> either reaches stoploss or target 3 (where we set to take profit): (1-0.68456)*0.92 + 0.684563*1.021 = 0.989
Simplistic model 2 -> either reaches target 3, or is sold off somewhere between stoploss and target 3 (assume uniform): ((0.92+1.02)/2)*(1-0.68) + 1.021*0.68 = 1.004

Decision: Wing it.

## Strategy - TODO


