import sys
from MasterTradePy.api import MasterTradeAPI
from MasterTradePy.model import (
    Basic,
    MarketTrader,
    Order,
    OrderQtyChange,
    OrderPriceChange,
    ReportOrder,
    SystemEvent,
    Inventory,
)
from MasterTradePy.constant import (
    Config,
    Exchange,
    PriceType,
    OrderType,
    TradingSession,
    Side,
    TradingUnit,
)
from MasterTradePy.helper import Helper
from MasterTradePy.constant import RCode
from MasterTradePy.soclient import SolClient, ServiceEventHandler, TradeMessageHandler
from MasterTradePy.utils import log
import os
import configparser
from time import sleep
import pandas as pd
from datetime import datetime
import lineTool


def line_print(msg):
    print(msg)
    try:
        # Line 推播
        token = "7CQD4kODYN0BM0OT3wkZWmYsJo683noaEYfPluzOBNB"
        lineTool.lineNotify(token, msg)
    except:
        print("line notify 失效")


class ConcreteMarketTrader(MarketTrader):
    def __init__(self):
        # 委託簿資料
        self.my_order_book = []
        self.my_book = []
        # 下單商品價格資料
        self.stock_basic = {}
        # 下單商品庫存
        self.stock_inventory = {}
        # 讀取設定文件 抓取策略必要設定
        self.config = configparser.ConfigParser()
        self.config.read("config.ini")
        self.symbol = self.config["parameters"]["symbol"]  # 交易商品
        self.strategy_amount = float(
            self.config["parameters"]["strategy_amount"]
        )  # 策略部位總額
        self.init_price = float(self.config["parameters"]["init_price"])  # 基準價
        self.init_ratio = float(self.config["parameters"]["init_ratio"])  # 初始單位數
        self.grid_gap = float(self.config["parameters"]["grid_gap"])  # 網格間距
        self.grid_unit = float(
            self.config["parameters"]["grid_unit"]
        )  # 每單位數(總數為100)
        self.up_down_grid_gap_diff = float(
            self.config["parameters"]["up_down_grid_gap_diff"]
        )  # 上漲下跌的網格間距差
        # 證券商帳號密碼
        self.username = self.config["account"]["ID"]
        self.password = self.config["account"]["password"]
        # 股票最小跳動點
        self.stock_price_list = (
            [i / 100 for i in range(1, 1001)]
            + [10 + (i / 100) for i in range(5, 4005, 5)]
            + [50 + (i / 10) for i in range(1, 501)]
            + [100 + (i / 10) for i in range(5, 4005, 5)]
            + [500 + (i) for i in range(1, 501)]
            + [1000 + (i) for i in range(5, 4005, 5)]
        )

    def OnNewOrderReply(self, data) -> None:
        print(data)

    def OnChangeReply(self, data) -> None:
        print(data)

    def OnCancelReply(self, data) -> None:
        print(data)

    def OnReport(self, data) -> None:
        if type(data) is ReportOrder:
            self.my_order_book.append(data.order)
            # 回報資料
            if data.order.tableName == "ORD:TwsOrd":  # 委託回報
                pass
                # print(f"回報資料: {data.order}")

            elif data.order.tableName == "RPT:TwsDeal":  # 成交回報
                pass
                # print(f"回報資料: {data.order}")

            elif data.order.tableName == "RPT:TwsNew":
                pass
                # print(f"回報資料: {data.order}")
            else:
                pass
                # print(f"回報資料: {data.order}")

    def OnReqResult(self, workID: str, data) -> None:
        if type(data) is Basic:
            self.stock_basic[data.symbol] = [
                data.refPrice,
                data.riseStopPrice,
                data.fallStopPrice,
            ]
            # 基本資料
            print(
                f"workid={workID}, 證券基本資料: 股票代號={data.symbol}, 參考價={data.refPrice},漲停價={data.riseStopPrice},跌停價={data.fallStopPrice}"
            )
        if type(data) is Inventory:
            # 庫存資料
            self.stock_inventory[data.symbol] = int(data.qty) + int(data.qtyZero)
            print(f"workid={workID}, 庫存資料={data}")

    def OnSystemEvent(self, data: SystemEvent) -> None:
        print(f"OnSystemEvent{data}")

    def OnAnnouncementEvent(self, data) -> None:
        print(f"OnAnnouncementEvent:{data}")

    def OnError(self, data):
        print(data)

    def ChangeGridArgu(self, change_price, change_unit):  # 修改網格基準價
        self.init_ratio += change_unit * self.grid_unit
        self.init_price = float(change_price)
        self.config["parameters"]["init_price"] = str(self.init_price)  # 基準價
        self.config["parameters"]["init_ratio"] = str(self.init_ratio)  # 初始單位數
        # 寫回config.ini檔案
        print(self.config["parameters"])
        with open("config.ini", "w") as configfile:
            self.config.write(configfile)

    def Login(self):
        is_sim = False
        is_force = True
        is_event = False
        # 登入
        self.api = MasterTradeAPI(self)
        self.api.SetConnectionHost("solace140.masterlink.com.tw:55555")
        rc = self.api.Login(self.username, self.password, is_sim, is_force, is_event)
        # 雙因子認證
        self.accounts = [x[4:] for x in self.api.accounts]
        rcc = self.api.CheckAccs(tradingAccounts=self.accounts)

    def GetOrderStatus(self):  # 找出委託中的最新狀況
        # 再送一次委託查詢
        self.api.QryRepAll(self.accounts[0])
        sleep(0.5)
        # 　將所有委託設定轉換為 dataframe
        order_book_data = pd.DataFrame(self.my_order_book)

        if len(self.my_order_book) > 0:
            all_row = []
            for ordNo in order_book_data["ordNo"].unique():
                tmp_order_book_data = order_book_data[
                    order_book_data["ordNo"] == ordNo
                ].copy()
                latest_row = tmp_order_book_data.iloc[0].copy()
                if tmp_order_book_data.shape[0] > 1:
                    for index, row in tmp_order_book_data.iloc[1:].iterrows():
                        latest_row["lastdealTime"] = row["lastdealTime"]
                        latest_row["status"] = row["status"]
                        latest_row["leavesQty"] = row["leavesQty"]
                        latest_row["cumQty"] = row["cumQty"]
                        latest_row["dealPri"] = row["dealPri"]
                all_row.append(latest_row)
            latest_data = pd.concat(all_row, axis=1).transpose()

            latest_data["trxTime"] = pd.to_datetime(
                datetime.now().strftime("%Y%m%d") + " " + latest_data["trxTime"],
                format="%Y%m%d %H:%M:%S.%f",
            )
            latest_data = latest_data[(latest_data["symbol"] == self.symbol)].copy()
            return latest_data
        else:
            return pd.DataFrame()

    def DeleteAllOrder(self):  # 刪除所有未成交
        # 找出未成交單
        latest_data = self.GetOrderStatus()

        if latest_data.shape[0] > 0:
            order_data = latest_data[
                (latest_data["leavesQty"] != "0")
                & (latest_data.status.str[:3] == "101")
                & (latest_data["symbol"] == self.symbol)
            ]
            # 依序將未成交單刪除
            for index, row in order_data.iterrows():
                print(f'{row["ordNo"]} 刪單')
                replaceOrder = OrderQtyChange(
                    ordNo=row["ordNo"], qty="0", tradingAccount=self.accounts[0]
                )
                self.api.ChangeOrderQty(replaceOrder)

    def OrderStockLMT(self, bs, symbol, price, qty):  # 網格下單
        odd_qty = qty % 1000
        normal_qty = qty - odd_qty
        # 先下整股
        order_side = Side.Buy
        if bs == "Buy":
            order_side = Side.Buy
        elif bs == "Sell":
            order_side = Side.Sell
        else:
            return
        if normal_qty != 0:
            order = Order(
                tradingSession=TradingSession.NORMAL,
                side=order_side,
                symbol=self.symbol,
                priceType=PriceType.LMT,
                price=str(price),
                tradingUnit=TradingUnit.COMMON,
                qty=str(normal_qty),
                orderType=OrderType.ROD,
                tradingAccount=self.accounts[0],
                userDef="",
            )
            rcode = self.api.NewOrder(order)
        # 再下零股
        if odd_qty != 0:
            order = Order(
                tradingSession=TradingSession.ODD,
                side=order_side,
                symbol=self.symbol,
                priceType=PriceType.LMT,
                price=str(price),
                tradingUnit=TradingUnit.ODD,
                qty=str(odd_qty),
                orderType=OrderType.ROD,
                tradingAccount=self.accounts[0],
                userDef="",
            )
            rcode = self.api.NewOrder(order)

    def RunStrategyOrder(self):  # 網格佈單

        # 查詢股價的漲跌停價
        self.api.ReqBasic(self.symbol)
        # 無限迴圈判斷 symbol 的基本資料回傳
        while self.stock_basic.get(self.symbol) == None:
            pass

        # 抓出漲跌停價價位
        stock_ceil = float(self.stock_basic[self.symbol][1])
        stock_floor = float(self.stock_basic[self.symbol][2])

        # 查詢庫存以後計算出場數量
        self.api.ReqInventoryRayinTotal(self.accounts[0])  # 查詢庫存
        # 無限迴圈判斷 symbol 的庫存資料回傳
        while self.stock_inventory.get(self.symbol) == None:
            pass

        # 庫存出場單位股數 = 庫存股數 / (庫存比例/每單位比例)
        inventory_qty = self.stock_inventory.get(self.symbol)
        line_print(
            f"蛛網佈單\n"
            + f"商品:{self.symbol}\n"
            + f"漲停:{stock_ceil}\n"
            + f"跌停:{stock_floor}\n"
            + f"蛛網基準:{self.init_price}\n"
            + f"目前佔策略資金持有比例:{self.init_ratio}%\n"
            + f"庫存總股數:{inventory_qty}\n"
            + f"理論庫存剩餘單位數:{(self.init_ratio/self.grid_unit)}"
        )

        # 向下掛出當日買進價位
        tmp_init_price = self.init_price * (1 - self.grid_gap)
        tmp_init_ratio = self.init_ratio + self.grid_unit
        # 檢查買進價位 還沒超出跌停價 以及 買進單位還沒超過上限
        while tmp_init_price >= stock_floor and round(tmp_init_ratio) < 100:
            # 找出可以下單的價格跳動點
            excute_price = min(
                [i for i in self.stock_price_list if i >= round(tmp_init_price, 2)]
            )
            # 掛出相對應的價位數量
            # 委託股數 = 單次投入金額 / 股價
            # (單次投入金額 = 策略金額 * 每單位%數)
            singal_order_amount = self.strategy_amount * (self.grid_unit / 100)
            singal_order_qty = int(singal_order_amount / excute_price)
            line_print(
                f"買\n"
                + f"策略基準價:{round(tmp_init_price,2)}\n"
                + f"策略單位:{tmp_init_ratio/self.grid_unit}\n"
                + f"委託價:{excute_price}\n"
                + f"委託總額:{singal_order_amount}\n"
                + f"委託股數:{singal_order_qty}"
            )
            # 送出委託單
            self.OrderStockLMT("Buy", self.symbol, excute_price, singal_order_qty)
            # 委託單價 向下調整
            tmp_init_price *= 1 - self.grid_gap
            tmp_init_ratio += self.grid_unit

        # 向上掛出當日賣出價位
        tmp_init_price = self.init_price * (
            1 + self.grid_gap * self.up_down_grid_gap_diff
        )
        tmp_init_ratio = self.init_ratio - self.grid_unit
        # 檢查買進價位 還沒超出漲停價 以及 賣出單位還沒超過下限
        while tmp_init_price <= stock_ceil and round(tmp_init_ratio) > 0:
            # 找出可以下單的價格跳動點
            excute_price = max(
                [i for i in self.stock_price_list if i <= round(tmp_init_price, 2)]
            )
            # 掛出相對應的價位數量
            singal_cover_price = excute_price
            # 計算要賣出的單位數量
            singal_cover_qty = int(inventory_qty / (self.init_ratio / self.grid_unit))
            line_print(
                f"賣\n"
                + f"策略基準價:{round(tmp_init_price,2)}\n"
                + f"第N單位:{tmp_init_ratio/self.grid_unit}\n"
                + f"委託價:{excute_price}\n"
                + f"委託股數:{singal_cover_qty}"
            )
            # 送出委託單
            self.OrderStockLMT("Sell", self.symbol, excute_price, singal_cover_qty)
            # 委託單價 向上調整
            tmp_init_price *= 1 + self.grid_gap * self.up_down_grid_gap_diff
            tmp_init_ratio -= self.grid_unit


if __name__ == "__main__":
    # 紀錄盤前時間
    record_time = datetime.now()
    # 實例化下單物件
    trade = ConcreteMarketTrader()
    # 登入
    trade.Login()
    # 全部刪單
    trade.DeleteAllOrder()
    # 策略式下單
    trade.RunStrategyOrder()

    # 每5分鐘偵測一次
    while True:
        sleep(300)
        if (
            datetime.now().strftime("%H%M") <= "0830"
            or datetime.now().strftime("%H%M") >= "1330"
        ):
            break
        print(f"{datetime.now()} 判斷一次")
        # 取得所有最新委託單
        symbol_order_status = trade.GetOrderStatus()
        if symbol_order_status.shape[0] == 0:
            print(f"尚無委託紀錄")
            continue

        # 取得所有未刪單的委託紀錄(在每次紀錄點以後)
        symbol_not_delete_data = symbol_order_status[
            ~(
                (symbol_order_status["status"].str[:3] == "101")
                & (symbol_order_status["leavesQty"] == "0")
            )
            & (symbol_order_status["trxTime"] > record_time)
        ]

        # 抓到每一個買賣、點位
        bs_price = symbol_not_delete_data[["side", "price"]].values.tolist()
        unique_bs_price = list(set(tuple(item) for item in bs_price))
        all_deal = []
        for bs, price in unique_bs_price:
            singal_order = symbol_not_delete_data[
                (symbol_not_delete_data["side"] == bs)
                & (symbol_not_delete_data["price"] == price)
            ]
            # 判斷這個點位是否完全成交
            if (singal_order["status"].str[:3] == "111").sum() == singal_order.shape[0]:
                deal_qty = singal_order["qty"].astype(float).sum()
                all_deal.append(
                    [bs, price, deal_qty, singal_order["lastdealTime"].max()]
                )

        if all_deal != []:
            # 把帳務記錄下來
            symbol_order_status.to_csv(
                f"元富帳務_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            )
            buy_deal_len = len([i for i in all_deal if i[0] == "B"])
            sell_deal_len = len([i for i in all_deal if i[0] == "S"])
            latest_time = max([i[3] for i in all_deal])
            latest_deal_price = [i[1] for i in all_deal if i[3] == latest_time][0]
            deal_num = buy_deal_len - sell_deal_len
            if deal_num > 0:
                line_print(f"\n買方成交{deal_num}單位\n新基準價:{latest_deal_price}")
            elif deal_num < 0:
                line_print(f"\n賣方成交{deal_num}單位\n新基準價:{latest_deal_price}")
            else:
                line_print(f"\n買賣方皆成交\n新基準價:{latest_deal_price}")

            trade.ChangeGridArgu(latest_deal_price, deal_num)
            record_time = datetime.now()
            trade.DeleteAllOrder()
            trade.RunStrategyOrder()
        else:
            print(f"判斷沒有新的成交紀錄")
