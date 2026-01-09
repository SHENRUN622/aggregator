#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AllTick A股行情工具（Python 3.5 兼容）

功能：
1. 输入股票代码（如 600519 / 000001 / 300750）
2. 调用 AllTick API 获取最新价格与日线 K 线
3. 计算 MA10、MA20 并输出

可用环境变量：
  - ALLTICK_BASE_URL: API 基础地址，默认 https://quote.alltick.io
  - ALLTICK_API_KEY: API Token，可同时作为 query param 或 Authorization Bearer
"""

from __future__ import print_function

import argparse
import json
import os
import sys

try:
    from urllib import request as urlrequest
    from urllib import parse as urlparse
except ImportError:  # pragma: no cover - python2 fallback (not required but safe)
    import urllib2 as urlrequest
    import urlparse


DEFAULT_BASE_URL = "https://quote.alltick.io"
DEFAULT_QUOTE_ENDPOINT = "/quote"
DEFAULT_KLINE_ENDPOINT = "/kline"


def build_symbol(code, market=None, format_type="dot"):
    """根据股票代码推断交易所并输出 AllTick 识别的 symbol。"""
    code = code.strip().upper()
    if market:
        market = market.strip().upper()
    else:
        # 简单规则：6开头走上交所，其余常见 A 股代码走深交所
        if code.startswith("6"):
            market = "SH"
        elif code.startswith(("0", "3")):
            market = "SZ"
        else:
            market = "SH"
    if format_type == "concat":
        return "{}{}".format(market, code)
    return "{}.{}".format(market, code)


def join_url(base, endpoint):
    """拼接 base url 与 endpoint。"""
    if not base:
        return endpoint
    base = base.rstrip("/")
    endpoint = endpoint if endpoint.startswith("/") else "/" + endpoint
    return base + endpoint


def http_get(url, params=None, headers=None, timeout=10):
    """使用 urllib 发起 GET 请求，兼容 Python 3.5。"""
    if params:
        query = urlparse.urlencode(params)
        url = "{}?{}".format(url, query)
    req = urlrequest.Request(url)
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    resp = urlrequest.urlopen(req, timeout=timeout)
    content = resp.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8", "ignore")
    return content


def parse_json(payload):
    """安全解析 JSON，失败时返回 None。"""
    try:
        return json.loads(payload)
    except ValueError:
        return None


def unwrap_data(payload):
    """适配不同 AllTick 响应结构，取出可能的 data 字段。"""
    if isinstance(payload, dict):
        for key in ("data", "result", "quote", "items"):
            if key in payload:
                return payload[key]
    return payload


def extract_latest_price(payload):
    """从 quote 响应中提取最新价字段。"""
    data = unwrap_data(payload)
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        for key in ("last", "price", "lastPrice", "last_price", "close", "closePrice"):
            if key in data:
                return float(data[key])
    return None


def extract_kline_closes(payload):
    """从 K 线响应中抽取收盘价列表。"""
    data = unwrap_data(payload)
    if isinstance(data, dict):
        for key in ("klines", "bars", "candles", "kline", "data"):
            if key in data:
                data = data[key]
                break
    closes = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key in ("close", "c", "closePrice", "close_price"):
                    if key in item:
                        closes.append(float(item[key]))
                        break
            elif isinstance(item, (list, tuple)) and item:
                if len(item) >= 5:
                    closes.append(float(item[4]))
                else:
                    closes.append(float(item[-1]))
    return closes


def moving_average(values, window):
    """计算最近 window 个收盘价的移动平均。"""
    if not values or len(values) < window:
        return None
    return sum(values[-window:]) / float(window)


def build_headers(token):
    """构建请求头。"""
    headers = {}
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    return headers


def main():
    parser = argparse.ArgumentParser(description="AllTick A股行情查询工具")
    parser.add_argument("code", help="A股股票代码，例如 600519 或 000001")
    parser.add_argument("--market", help="市场前缀 SH/SZ，可选", default=None)
    parser.add_argument(
        "--symbol-format",
        choices=["dot", "concat"],
        default="dot",
        help="交易所与代码拼接方式：dot=SH.600519，concat=SH600519",
    )
    parser.add_argument("--token", help="AllTick API Token", default=os.getenv("ALLTICK_API_KEY", ""))
    parser.add_argument(
        "--base-url",
        default=os.getenv("ALLTICK_BASE_URL", DEFAULT_BASE_URL),
        help="AllTick API Base URL",
    )
    parser.add_argument("--quote-endpoint", default=DEFAULT_QUOTE_ENDPOINT, help="最新价接口路径")
    parser.add_argument("--kline-endpoint", default=DEFAULT_KLINE_ENDPOINT, help="日线 K 线接口路径")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP 超时时间（秒）")
    args = parser.parse_args()

    symbol = build_symbol(args.code, market=args.market, format_type=args.symbol_format)
    headers = build_headers(args.token)

    quote_url = join_url(args.base_url, args.quote_endpoint)
    kline_url = join_url(args.base_url, args.kline_endpoint)

    quote_params = {"symbol": symbol}
    kline_params = {"symbol": symbol, "interval": "1d", "count": 20}
    if args.token:
        quote_params["token"] = args.token
        kline_params["token"] = args.token

    try:
        quote_payload = http_get(quote_url, params=quote_params, headers=headers, timeout=args.timeout)
        quote_json = parse_json(quote_payload)
    except Exception as exc:
        print("获取最新价失败: {}".format(exc))
        return 1

    try:
        kline_payload = http_get(kline_url, params=kline_params, headers=headers, timeout=args.timeout)
        kline_json = parse_json(kline_payload)
    except Exception as exc:
        print("获取K线失败: {}".format(exc))
        return 1

    latest_price = extract_latest_price(quote_json)
    closes = extract_kline_closes(kline_json)
    ma10 = moving_average(closes, 10)
    ma20 = moving_average(closes, 20)

    print("股票代码: {} ({})".format(args.code, symbol))
    if latest_price is None:
        print("最新价: 无法解析")
    else:
        print("最新价: {:.4f}".format(latest_price))

    if ma10 is None:
        print("MA10: 数据不足或解析失败")
    else:
        print("MA10: {:.4f}".format(ma10))

    if ma20 is None:
        print("MA20: 数据不足或解析失败")
    else:
        print("MA20: {:.4f}".format(ma20))

    return 0


if __name__ == "__main__":
    sys.exit(main())
