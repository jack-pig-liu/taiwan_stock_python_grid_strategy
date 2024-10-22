import pandas as pd
from json import loads
import requests
import os
from datetime import datetime


class trade:
    def __init__(self, init_time, init_price, init_unit):

        # 建立交易明細表
        self.position_table = pd.DataFrame(
            {
                "進場時間": [init_time] * init_unit,
                "進場價格": [init_price] * init_unit,
                "出場時間": [None] * init_unit,
                "出場價格": [None] * init_unit,
            }
        )

        # 股票最小跳動點價格集合
        self.stock_price_list = (
            [i / 100 for i in range(1, 1001)]
            + [10 + (i / 100) for i in range(5, 4005, 5)]
            + [50 + (i / 10) for i in range(1, 501)]
            + [100 + (i / 10) for i in range(5, 4005, 5)]
            + [500 + (i) for i in range(1, 501)]
            + [1000 + (i) for i in range(5, 4005, 5)]
        )

    def position(self):  # 查在倉部位
        return self.position_table[self.position_table["出場時間"].isna()].shape[0]

    def cover(self, time, price):  # 平倉
        excute_price = max([i for i in self.stock_price_list if i <= round(price, 2)])
        for index, row in self.position_table.iterrows():
            if row["出場時間"] is None:
                self.position_table.loc[index, "出場時間"] = time
                self.position_table.loc[index, "出場價格"] = excute_price
                break

    def order(self, time, price):  # 新倉
        excute_price = min([i for i in self.stock_price_list if i >= round(price, 2)])
        new_trade = pd.DataFrame(
            [[time, excute_price, None, None, self.position() + 1]]
        )
        new_trade.columns = [
            "進場時間",
            "進場價格",
            "出場時間",
            "出場價格",
            "買進後持有",
        ]
        self.position_table = pd.concat([self.position_table, new_trade])
        self.position_table.reset_index(drop=True, inplace=True)

    def convertYearFormat(self, date):  # 轉換年分
        # date = '108年01月02日'
        date1 = date.replace("年", "-").replace("月", "-").replace("日", "")
        date2 = date1.split("-")
        date3 = "-".join([str(int(date2[0]) + 1911), date2[1], date2[2]])
        return date3

    def restoreReturn(self, symbol):
        dirname = "data"
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        dividend_filename = f"{dirname}/上市除權息表.csv"
        if not os.path.exists(dividend_filename):
            today = datetime.now().strftime("%Y%m%d")
            url = f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=20080101&endDate={today}&response=json&_=1706148539236"
            html = requests.get(url)
            dividend_data = loads(html.text)
            dividend_table = pd.DataFrame(
                dividend_data["data"], columns=dividend_data["fields"]
            )
            dividend_table.to_csv(dividend_filename, index=False, encoding="cp950")

        # 取得除權息數據
        dividend_table = pd.read_csv(dividend_filename, encoding="cp950")
        # 民國日期處理
        dividend_table["西元日期"] = dividend_table["資料日期"].apply(
            self.convertYearFormat
        )
        dividend_table_one = dividend_table[dividend_table["股票代號"] == symbol]
        dividend_table_one["西元日期"] = pd.to_datetime(
            dividend_table_one["西元日期"] + " 09:00"
        )

        # 判斷 每一筆交易 當中有沒有包含除權息的資料
        self.position_table["還原除權息"] = 0
        for index, row in self.position_table[
            self.position_table["出場時間"].notna()
        ].iterrows():
            # 每一筆交易明細 都要判斷每個除權息日
            for index1, row1 in dividend_table_one.iterrows():
                if (row["進場時間"] <= row1["西元日期"]) and (
                    row["出場時間"] >= row1["西元日期"]
                ):
                    self.position_table.loc[index, "還原除權息"] += row1["權值+息值"]
