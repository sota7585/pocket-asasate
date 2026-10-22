"""朝7時のまとめ（モーニングサテライトの代わり）を作る。

- アメリカの市場・為替・原油や金・金利 … yfinance
- 今日の日経平均の始まりの目安 … 日経平均先物（シカゴ・円建て）と日経平均の前日終値の差
- 前日の値上がり上位 … 前日の「後場の終わり」の記録
- ニュース … Google ニュースの検索結果（RSS）
"""

import json
from datetime import datetime

import pandas as pd
import yfinance as yf

import company_info
import ranking

MORNING_DIR = ranking.DATA_DIR / "morning"

# 表示名, 記号, 単位, 小数点以下の桁数
US_MARKET = [
    ("NYダウ", "^DJI", "ドル", 0),
    ("S&P500", "^GSPC", "", 0),
    ("ナスダック", "^IXIC", "", 0),
    ("半導体株指数（SOX）", "^SOX", "", 0),
]
OTHERS = [
    ("ドル円", "USDJPY=X", "円", 2),
    ("原油（WTI）", "CL=F", "ドル", 2),
    ("金", "GC=F", "ドル", 1),
    ("米10年債利回り", "^TNX", "%", 2),
    ("恐怖指数（VIX）", "^VIX", "", 2),
]
FUTURES = "NIY=F"   # 日経平均先物（シカゴ・円建て）
NIKKEI = "^N225"

NEWS_QUERIES = [
    ("アメリカの市場", "米国株 市況 when:1d"),
    ("日本の市場・見通し", "日経平均 見通し when:1d"),
    ("会社の発表・決算", "決算 発表 株価 when:1d"),
]


def _quotes(symbols: list[str]) -> dict[str, dict]:
    """それぞれの最新の値と、前の日からの変化を返す。"""
    data = yf.download(symbols, period="10d", interval="1d", group_by="ticker",
                       auto_adjust=False, progress=False)
    out = {}
    for s in symbols:
        p = data[s]["Close"].dropna() if s in data.columns.get_level_values(0) else pd.Series(dtype=float)
        if len(p) < 2:
            continue
        last, prev = float(p.iloc[-1]), float(p.iloc[-2])
        out[s] = {
            "value": last,
            "change": last - prev,
            "change_pct": (last / prev - 1) * 100,
            "date": p.index[-1].strftime("%Y-%m-%d"),
        }
    return out


def _previous_top() -> dict | None:
    """一番新しい「後場の終わり」の記録（＝前の取引日の値上がり上位）。"""
    for s in ranking.list_snapshots():
        if s["timing"] == "close_pm":
            return s
    return None


def build_summary() -> dict:
    symbols = [s for _, s, _, _ in US_MARKET + OTHERS] + [FUTURES, NIKKEI]
    q = _quotes(symbols)

    def rows(items):
        return [{"label": label, "symbol": s, "unit": unit, "digits": d, **q[s]}
                for label, s, unit, d in items if s in q]

    # 今日の始まりの目安：先物が日経平均の前日終値よりどれだけ高いか（安いか）
    outlook = None
    if FUTURES in q and NIKKEI in q:
        nikkei_close = q[NIKKEI]["value"]
        fut = q[FUTURES]["value"]
        outlook = {
            "nikkei_close": nikkei_close,
            "futures": fut,
            "diff": fut - nikkei_close,
            "diff_pct": (fut / nikkei_close - 1) * 100,
        }

    news = []
    seen = set()
    for label, query in NEWS_QUERIES:
        items = []
        for n in company_info.search_news(query, limit=8):
            if n["title"] in seen:
                continue
            seen.add(n["title"])
            items.append(n)
            if len(items) == 4:
                break
        news.append({"label": label, "items": items})

    prev = _previous_top()
    return {
        "created_at": datetime.now(ranking.JST).isoformat(timespec="minutes"),
        "us_market": rows(US_MARKET),
        "others": rows(OTHERS),
        "outlook": outlook,
        "previous_top": prev,
        "news": news,
    }


def save_summary(summary: dict) -> None:
    MORNING_DIR.mkdir(parents=True, exist_ok=True)
    day = summary["created_at"][:10]
    (MORNING_DIR / f"{day}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


def load_latest() -> dict | None:
    if not MORNING_DIR.exists():
        return None
    files = sorted(MORNING_DIR.glob("*.json"), reverse=True)
    return json.loads(files[0].read_text(encoding="utf-8-sig")) if files else None


# ---- 表示用 ----

def fmt_quote(r: dict) -> str:
    """例: 52,495ドル（+529、+1.0%）"""
    d = r["digits"]
    sign = "+" if r["change"] >= 0 else ""
    return (f"{r['value']:,.{d}f}{r['unit']}"
            f"（{sign}{r['change']:,.{d}f}、{sign}{r['change_pct']:.1f}%）")


def outlook_text(o: dict | None) -> str:
    if not o:
        return "先物の値が取れませんでした"
    sign = "+" if o["diff"] >= 0 else ""
    if o["diff_pct"] >= 0.3:
        mood = "高く始まりそう"
    elif o["diff_pct"] <= -0.3:
        mood = "安く始まりそう"
    else:
        mood = "前日と同じくらいで始まりそう"
    return (f"日経平均先物 {o['futures']:,.0f}円（前日の日経平均 {o['nikkei_close']:,.0f}円より"
            f" {sign}{o['diff']:,.0f}円、{sign}{o['diff_pct']:.1f}%）→ **{mood}**")


def _join_within(lines: list[str], limit: int = 4000) -> str:
    """Discord の文字数の上限を超えないところまで行をつなげる（リンクの途中で切らない）。"""
    out, total = [], 0
    for line in lines:
        if total + len(line) + 1 > limit:
            break
        out.append(line)
        total += len(line) + 1
    return "\n".join(out).strip()


def build_messages(s: dict) -> list[dict]:
    """Discord に送る中身。1通の文字数に上限があるので、まとめとニュースの2通に分ける。"""
    us = "\n".join(f"{r['label']}　{fmt_quote(r)}" for r in s["us_market"])
    others = "\n".join(f"{r['label']}　{fmt_quote(r)}" for r in s["others"])

    prev_lines = []
    p = s["previous_top"]
    if p:
        for i, r in enumerate(p["rows"], 1):
            prev_lines.append(f"{i}. [{r['name']}]({company_info.kabutan_url(r['code'])})"
                              f"（{r['sector']}） **+{r['change_pct']:.1f}%**")
    prev = "\n".join(prev_lines) or "記録がありません"

    news_lines = []
    for group in s["news"]:
        news_lines.append(f"**{group['label']}**")
        for n in group["items"][:3]:
            news_lines.append(f"・[{n['title'][:60]}]({n['link']})")
        news_lines.append("")

    created = datetime.fromisoformat(s["created_at"])
    return [
        {"embeds": [
            {"title": f"🌅 朝のまとめ　{created:%m/%d}", "color": 0xF2A33A,
             "description": "**今日の始まりの目安**\n" + outlook_text(s["outlook"])},
            {"title": "🇺🇸 アメリカの市場（前日の終値）", "color": 0x3B6FD8, "description": us},
            {"title": "💱 為替・原油・金・金利", "color": 0x8A63D2, "description": others},
            {"title": "📈 前日の値上がり上位10社", "color": 0x2E9E5B, "description": prev},
        ]},
        {"embeds": [
            {"title": "📰 今朝のニュース", "color": 0x777777, "description": _join_within(news_lines)},
        ]},
    ]


if __name__ == "__main__":
    import notify

    summary = build_summary()
    save_summary(summary)
    for payload in build_messages(summary):
        notify.send(payload)
