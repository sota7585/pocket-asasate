"""会社ごとの詳しい情報（指標とニュース）を集める。

- 指標は yfinance（Yahoo Finance）から取得
- ニュースは Google ニュースの検索結果（RSS）から取得
"""

import math
import unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
import yfinance as yf

from ranking import JST


def _num(v):
    """数字として使えない値（None や NaN）は None にそろえる。"""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _latest(bs, *names):
    """決算の表から、一番新しい期の値を取り出す。"""
    for n in names:
        if n in bs.index:
            for v in bs.loc[n]:
                v = _num(v)
                if v is not None:
                    return v
    return None


def fetch_metrics(code: str) -> dict:
    """PBR・PER・時価総額・ROE・有利子負債・ネットキャッシュ比率を返す。取れないものは None。"""
    t = yf.Ticker(f"{code}.T")
    try:
        info = t.info
    except Exception:
        info = {}
    try:
        bs = t.quarterly_balance_sheet
        if bs is None or bs.empty:
            bs = t.balance_sheet
    except Exception:
        bs = None

    market_cap = _num(info.get("marketCap"))
    roe = _num(info.get("returnOnEquity"))
    debt = _num(info.get("totalDebt"))
    if debt is None and bs is not None and not bs.empty:
        debt = _latest(bs, "Total Debt")

    # ネットキャッシュ比率（清原式）
    # ＝（流動資産 ＋ 投資有価証券 × 0.7 − 負債合計）÷ 時価総額
    net_cash_ratio = None
    if bs is not None and not bs.empty and market_cap:
        current_assets = _latest(bs, "Current Assets")
        securities = _latest(bs, "Investmentin Financial Assets", "Available For Sale Securities") or 0
        liabilities = _latest(bs, "Total Liabilities Net Minority Interest")
        if current_assets is not None and liabilities is not None:
            net_cash_ratio = (current_assets + securities * 0.7 - liabilities) / market_cap

    return {
        "per": _num(info.get("trailingPE")),
        "pbr": _num(info.get("priceToBook")),
        "market_cap": market_cap,
        "roe": roe * 100 if roe is not None else None,
        "debt": debt if debt is not None else 0.0 if bs is not None and not bs.empty else None,
        "net_cash_ratio": net_cash_ratio,
    }


def fetch_news(name: str, limit: int = 5) -> list[dict]:
    """会社名で株のニュースを検索して、新しい順に返す。"""
    # JPX の会社名は全角英数字（ＧＭＯ など）なので、検索しやすい半角にそろえる
    return search_news(f'"{unicodedata.normalize("NFKC", name)}" 株', limit)


def search_news(query: str, limit: int = 5) -> list[dict]:
    """Google ニュースを検索して、新しい順に返す。"""
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:
        return []
    items = []
    for it in root.iter("item"):
        try:
            published = parsedate_to_datetime(it.findtext("pubDate")).astimezone(JST)
        except Exception:
            published = None
        source = it.findtext("source", "")
        title = it.findtext("title", "")
        # 見出しの最後に付いている「 - 配信元」を外す
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")]
        items.append({
            "title": title,
            "link": it.findtext("link", ""),
            "source": source,
            "published": published.isoformat(timespec="minutes") if published else None,
        })
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items[:limit]


def kabutan_url(code: str) -> str:
    return f"https://kabutan.jp/stock/?code={code}"


# ---- 表示用の書き方 ----

def fmt_yen(v) -> str:
    """金額を「億円」でそろえて書く。"""
    if v is None:
        return "—"
    if v == 0:
        return "0円"
    oku = v / 100_000_000
    if abs(oku) >= 10_000:
        return f"{oku / 10_000:,.2f}兆円"
    if abs(oku) >= 10:
        return f"{oku:,.0f}億円"
    return f"{oku:,.1f}億円"


def fmt_times(v) -> str:
    return "—" if v is None else f"{v:.1f}倍"


def fmt_pct(v) -> str:
    return "—" if v is None else f"{v:.1f}%"


def fmt_ratio(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def summary_line(m: dict) -> str:
    """Discord 用に、指標を1行にまとめる。"""
    return (
        f"PER {fmt_times(m['per'])}・PBR {fmt_times(m['pbr'])}・時価 {fmt_yen(m['market_cap'])}"
        f"・ROE {fmt_pct(m['roe'])}・有利子負債 {fmt_yen(m['debt'])}・NC比率 {fmt_ratio(m['net_cash_ratio'])}"
    )
