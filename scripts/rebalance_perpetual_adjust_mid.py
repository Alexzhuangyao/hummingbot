from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.strategy.script_strategy_base import Decimal, OrderType, ScriptStrategyBase
from typing import Dict

from hummingbot.core.event.events import OrderFilledEvent, OrderType, TradeType
from hummingbot.core.data_type import common
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase

from hummingbot.core.utils.async_utils import safe_ensure_future


class RebalancePerptual(ScriptStrategyBase):
    """
    自动平衡+盘口挂单
    """
    def __init__(self, connectors: Dict[str, ConnectorBase]):
        # 设定变量
        super().__init__(connectors)
        self.current_timestamp = None
        self.config: Dict = {
            "connector_name": "binance_perpetual_testnet",
            "trading_pair": {"BNB-BUSD", "ADA-BUSD", "DOGE-BUSD",
                             "AVAX-BUSD", "APT-BUSD"},
            "threshold": Decimal("0.01"),
            "targe_value": Decimal("2000"),
            "buy_interval": 60,
            "test_volume": 50
        }
        self.last_ordered_ts = 0.
        self.markets = {self.config["connector_name"]: self.config["trading_pair"]}
        self.connector = self.connectors[self.config["connector_name"]]
        self.price = {}
        self.asset_value = {}

    def on_tick(self):
        # 检查是否到了买入时间，
        if self.last_ordered_ts < (self.current_timestamp - self.config["buy_interval"]):
            self.cancel_all_order()
            self.get_balance()
            self.create_order()
            self.last_ordered_ts = self.current_timestamp

    # 取消所有订单
    def cancel_all_order(self):
        for exchange in self.connectors.values():
            safe_ensure_future(exchange.cancel_all(timeout_seconds=6))

    # 获取当前持仓状况
    def get_balance(self):
        positions = self.connectors[self.config["connector_name"]].account_positions
        if positions:
            for tp in self.config["trading_pair"]:
                amount = Decimal(positions[tp.replace("-", "")].amount)  # 不同交易所这里的字符串可能不同
                price = Decimal(self.connectors[self.config["connector_name"]].get_mid_price(tp))
                self.price[tp] = price
                self.asset_value[tp] = amount * price
        print(self.asset_value)

    # 下订单
    def create_order(self):
        # 计算当前资产的价值，换算成USDT
        # 如果资产的价值大于目标价值+阈值，挂单卖出
        # 如果资产的价值小于目标价值+阈值，挂单买入
        # 如果两者都不是，则同时挂较远的买卖订单
        config = self.config.copy()
        for tp in self.asset_value:
            if self.asset_value[tp] >= config["targe_value"] * (1 + config["threshold"]):
                self.sell(self.config["connector_name"], tp,
                          Decimal(config["targe_value"] * config["threshold"]) / self.price[tp], OrderType.LIMIT,
                          self.price[tp] * Decimal("1.001"), common.PositionAction.CLOSE)
            elif self.asset_value[tp] < config["targe_value"] * (1 - config["threshold"]):
                self.buy(self.config["connector_name"], tp,
                         Decimal(config["targe_value"] * config["threshold"]) / self.price[tp], OrderType.LIMIT,
                         self.price[tp] * Decimal("0.999"), common.PositionAction.OPEN)
            else:
                self.sell(self.config["connector_name"], tp,
                          Decimal(config["targe_value"] * config["threshold"]) / self.price[tp], OrderType.LIMIT,
                          self.price[tp] * Decimal("1.005"), common.PositionAction.CLOSE)
                self.buy(self.config["connector_name"], tp,
                         Decimal(config["targe_value"] * config["threshold"]) / self.price[tp], OrderType.LIMIT,
                         self.price[tp] * Decimal("0.995"), common.PositionAction.OPEN)

    def adjusted_mid_price(self, pair):
        """
        Returns the  price of a hypothetical buy and sell or the base asset where the amout is {strategy.test_volume}
        """
        ask_result = self.connector.get_quote_volume_for_base_amount(pair, True, self.config["test_volume"])
        bid_result = self.connector.get_quote_volume_for_base_amount(pair, False, self.config["test_volume"])
        average_ask = ask_result.result_volume / ask_result.query_volume
        average_bid = bid_result.result_volume / bid_result.query_volume
        return average_bid + ((average_ask - average_bid) / 2)

