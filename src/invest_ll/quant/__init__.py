"""Portfolio research engine: many assets, target weights, honest validation.

The single-asset and rotation engines in `invest_ll.engine` answer "what would this rule have done
with one position at a time". This package answers the questions a systematic fund asks before
risking money:

- **Which assets existed on that date?** `panel` and `universe` build a point-in-time universe from
  every pair Binance ever listed, dead ones included.
- **How much of each?** Strategies return target weights, so risk can be spread and sized.
- **What did it really cost?** `engine` charges commission and slippage on every trade, liquidates
  delisted coins, and can pay Spanish capital-gains tax from the account.
- **Is the result luck?** `validation` runs walk-forward selection, the probability of backtest
  overfitting (PBO) and the deflated Sharpe ratio.

Like the rest of the engine, nothing here touches the network (tests/unit/test_engine_isolation.py).
"""
