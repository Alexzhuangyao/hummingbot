import logging
from hummingbot.strategy.script_strategy_base import Decimal, OrderType, ScriptStrategyBase
from hummingbot.core.event.events import OrderFilledEvent, OrderType, TradeType
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from decimal import Decimal


class DigBTC(ScriptStrategyBase):
    trade_exchange = "gate_io"
    exchange1 = "binance"
    exchange2 = "okx"
    exchange3 = "huobi"
    trading_pair = "BTC-USDT"

    price_increment = Decimal("1")
    interval = 1
    order_amount = Decimal("0.0004")

    activate_order_id = {}

    asset_value = {}
    last_ordered_ts = 0.
    markets = {
        trade_exchange: {trading_pair},
        exchange1: {trading_pair},
        exchange2: {trading_pair},
        exchange3: {trading_pair}
    }
    pre_trend = 0
    pre_price_1 = 0
    pre_price_2 = 0
    pre_price_3 = 0

    price = Decimal("0")
    loop = 0

    def on_tick(self):
        # Check if it is time to buy
        # 检查是否到了买入时间,
        if self.last_ordered_ts < (self.current_timestamp - self.interval):
            self.cancel_all_orders()
            self.get_price()
            self.create_order()

            self.last_ordered_ts = self.current_timestamp
            self.loop += 1

    # 取消所有订单
    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.trade_exchange):
            self.cancel(self.trade_exchange, order.trading_pair, order.client_order_id)

    # 通过价格涨跌判断趋势
    def get_price(self):
        self.price = self.connectors[self.trade_exchange].get_mid_price(self.trading_pair)
        self.price_1 = self.connectors[self.exchange1].get_mid_price(self.trading_pair)
        self.price_2 = self.connectors[self.exchange2].get_mid_price(self.trading_pair)
        self.price_3 = self.connectors[self.exchange3].get_mid_price(self.trading_pair)

        self.trend, self.trend1, self.trend2, self.trend3 = 0, 0, 0, 0
        if self.price_1 > self.pre_price_1 + self.price_increment: self.trend1 = 1
        if self.price_2 > self.pre_price_2 + self.price_increment: self.trend2 = 1
        if self.price_3 > self.pre_price_3 + self.price_increment: self.trend3 = 1

        if self.price_1 < self.pre_price_1 - self.price_increment: self.trend1 = -1
        if self.price_2 < self.pre_price_2 - self.price_increment: self.trend2 = -1
        if self.price_3 < self.pre_price_3 - self.price_increment: self.trend3 = -1

        self.trend = self.trend1 + self.trend2 + self.trend3
        print(self.trend)
        # record price
        self.pre_price_1 = self.price_1
        self.pre_price_2 = self.price_2
        self.pre_price_3 = self.price_3
        self.pre_trend = self.trend
        self.loop += 1

    # 创建订单
    def create_order(self):
        # create order
        if self.trend >= 2 and self.loop > 0:
            price = self.connectors[self.trade_exchange].get_price(self.trading_pair, False) + 1
            self.buy(
                connector_name=self.trade_exchange,
                trading_pair=self.trading_pair,
                amount=self.order_amount,
                order_type=OrderType.LIMIT,
                price=price
            )
        if self.trend <= -2 and self.loop > 0:
            price = self.connectors[self.trade_exchange].get_price(self.trading_pair, True) - 1
            self.sell(
                connector_name=self.trade_exchange,
                trading_pair=self.trading_pair,
                amount=self.order_amount,
                order_type=OrderType.LIMIT,
                price=price
            )

    def did_fill_order(self, event: OrderFilledEvent):
        """
        Method called when the connector notifies that an order has been partially or totally filled (a trade happened)
        """
        #   self.trade_amount = self.trade_amount - float(event.amount)
        self.logger().info(logging.INFO, f"The order {event.order_id} has been filled")