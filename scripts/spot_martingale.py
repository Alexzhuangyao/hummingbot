import math
import logging
import os
from decimal import Decimal
from typing import Optional

import pandas as pd

from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type import common
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.event_forwarder import SourceInfoEventForwarder
from hummingbot.core.event.events import OrderBookEvent, OrderBookTradeEvent, OrderFilledEvent
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class SpotMartingale(ScriptStrategyBase):
    """
    spot martingale
    """
    connector_name = os.getenv("CONNECTOR_NAME", "binance_paper_trade")
    trading_pair = {"BTC-USDT"}
    trading_pair_avg_price = {i: {0:0} for i in trading_pair}
    position_amount_usd = Decimal(os.getenv("POSITION_AMOUNT_USD", "30"))
    markets = {connector_name: {trading_pair}}

    subscribed_to_order_book_trade_event: bool = False
    position: Optional[OrderFilledEvent] = None
    current_round = 0
    last_ordered_ts = 0
    buy_interval = 60

    def on_tick(self):
        if self.last_ordered_ts < (self.current_timestamp - self.buy_interval):
            try:
                self.cancel_all_order()
                self.start_martingale()
            finally:
                self.last_ordered_ts = self.current_timestamp

    def start_martingale(self):
        df = self.connectors[self.connector_name].account_positions
        for trading_pair in self.trading_pair:
            if self.current_round == 0:
                self.logger().info(logging.INFO, "无仓位，开仓挂买单")
                best_bid = Decimal(self.connectors[self.connector_name].get_price(trading_pair, False))
                self.buy(self.connector_name, trading_pair, self.order_amount_usd / best_bid, OrderType.LIMIT, best_bid,
                         common.PositionAction.OPEN)
                self.trading_pair_avg_price[trading_pair] = {self.order_amount_usd / best_bid: best_bid}
            else:
                self.logger().info(logging.INFO, "有仓位，挂止盈和补仓单")
                amount = Decimal(df[position_pair].amount)
                entry_price = Decimal(df[position_pair].entry_price)
                #止盈单
                if amount > 0:
                    #止盈单
                    takeprofit_price = max(entry_price * (1+self.take_profit), Decimal(self.connectors[self.connector_name].get_price(trading_pair, True)))
                    self.sell(self.connector_name, trading_pair, amount , OrderType.LIMIT, takeprofit_price, common.PositionAction.CLOSE)
                    #补仓单
                    buymore_amount = Decimal(abs(amount) * self.multiple)
                    self.adjust_grid(buymore_amount * entry_price)
                    buymore_price = min(Decimal(entry_price * (1 - self.buy_more * self.grid_multiple)), Decimal(self.connectors[self.connector_name].get_price(trading_pair,False)))
                    self.buy(self.connector_name, trading_pair, buymore_amount, OrderType.LIMIT, buymore_price, common.PositionAction.OPEN)
                elif amount < 0 :
                    # 止盈单
                    takeprofit_price = min(entry_price * (1 - self.take_profit),Decimal(self.connectors[self.connector_name].get_price(trading_pair, False)))
                    self.buy(self.connector_name, trading_pair, abs(amount), OrderType.LIMIT,takeprofit_price, common.PositionAction.CLOSE)
                    #补仓单
                    buymore_amount = Decimal(abs(amount) * self.multiple)
                    self.adjust_grid(buymore_amount * entry_price)
                    buymore_price = max(Decimal(entry_price * (1 + self.buy_more * self.grid_multiple)),Decimal(self.connectors[self.connector_name].get_price(trading_pair, True)))

                    self.sell(self.connector_name, trading_pair, buymore_amount,OrderType.LIMIT, buymore_price, common.PositionAction.OPEN)

    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.trade_exchange):
            self.cancel(self.trade_exchange, order.trading_pair, order.client_order_id)

    def create_order_candidate(self, order_side: bool) -> OrderCandidate:
        """
        Create and quantize order candidate.
        """
        connector: ConnectorBase = self.connectors[self.connector_name]
        is_buy = order_side == TradeType.BUY
        price = connector.get_price(self.trading_pair, is_buy)
        if is_buy:
            conversion_rate = RateOracle.get_instance().get_pair_rate(self.trading_pair)
            amount = self.position_amount_usd / conversion_rate
        else:
            amount = self.position.amount

        amount = connector.quantize_order_amount(self.trading_pair, amount)
        price = connector.quantize_order_price(self.trading_pair, price)
        return OrderCandidate(
            trading_pair=self.trading_pair,
            is_maker = False,
            order_type = OrderType.LIMIT,
            order_side = order_side,
            amount = amount,
            price = price)

    def format_status(self) -> str:
        """
        Returns status of the current strategy on user balances and current active orders. This function is called
        when status command is issued. Override this function to create custom status display output.
        """
        if not self.ready_to_trade:
            return "Market connectors are not ready."
        lines = []
        warning_lines = []
        warning_lines.extend(self.network_warning(self.get_market_trading_pair_tuples()))

        balance_df = self.get_balance_df()
        lines.extend(["", "  Balances:"] + ["    " + line for line in balance_df.to_string(index=False).split("\n")])

        try:
            df = self.active_orders_df()
            lines.extend(["", "  Orders:"] + ["    " + line for line in df.to_string(index=False).split("\n")])
        except ValueError:
            lines.extend(["", "  No active maker orders."])

        # Strategy specific info
        lines.extend(["", "  current round:"] + ["    " + f"{self.current_round}"])

        warning_lines.extend(self.balance_warning(self.get_market_trading_pair_tuples()))
        if len(warning_lines) > 0:
            lines.extend(["", "*** WARNINGS ***"] + warning_lines)
        return "\n".join(lines)
