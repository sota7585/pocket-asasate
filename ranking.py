"""値上がり上位を集める仕組み。

- 上場会社の一覧（業種つき）は JPX（日本取引所グループ）の公開ファイルから取得
- 株価は yfinance（Yahoo Finance）から取得。約20分遅れのデータ
"""

import io
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

DATA_DIR = Path(__file__).parent / "data"
LIST_FILE = DATA_DIR / "companies.csv"
SNAPSHOT_DIR = DATA_DIR / "snapshots"

JPX_PAGE = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
JST = ZoneInfo("Asia/Tokyo")

# 取引所が決めた区切り
TIMINGS = {
    "open_am": "朝の寄り付き後（9:00すぎ）",
    "close_am": "前場の終わり（11:30）",
    "open_pm": "後場の寄り付き（12:30すぎ）",
    "close_pm": "後場の終わり（15:30）",
    "manual": "手動で取得",
}


def update_company_list() -> pd.DataFrame:
    """JPXから上場会社一覧をダウンロードして保存する（月1回くらいで十分）。"""
    page = requests.get(JPX_PAGE, timeout=60)
    page.raise_for_status()
    links = re.findall(r'href="([^"]+data_j\.xlsx?)"', page.text)
    if not links:
        raise RuntimeError("JPXのページで上場会社一覧のファイルが見つかりませんでした")
    url = requests.compat.urljoin(JPX_PAGE, links[0])
    content = requests.get(url, timeout=60).content
    df = pd.read_excel(io.BytesIO(content), dtype={"コード": str})

    # 株式だけ残す（ETFやREITは除く）
    df = df[df["市場・商品区分"].str.contains("内国株式", na=False)]
    df = df.rename(columns={
        "コード": "code",
        "銘柄名": "name",
        "市場・商品区分": "market",
        "33業種区分": "sector",
    })[["code", "name", "market", "sector"]]
    df["market"] = df["market"].str.replace("（内国株式）", "", regex=False)

    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(LIST_FILE, index=False, encoding="utf-8-sig")
    return df


def load_company_list() -> pd.DataFrame:
    if not LIST_FILE.exists():
        return update_company_list()
    return pd.read_csv(LIST_FILE, dtype={"code": str}, encoding="utf-8-sig")


def fetch_top_gainers(top_n: int = 10, min_trading_value: float = 0) -> pd.DataFrame:
    """全上場株の値上がり率を計算して、上位 top_n 社を返す。

    min_trading_value: 売買代金（円）がこれ未満の会社は除く。
    """
    companies = load_company_list()
    prices = _download_prices([f"{c}.T" for c in companies["code"]])

    rows = []
    for code in companies["code"]:
        p = prices.get(f"{code}.T")
        if p is None or len(p) < 2:
            continue
        prev_close = p["Close"].iloc[-2]
        last = p["Close"].iloc[-1]
        volume = p["Volume"].iloc[-1]
        if not prev_close:
            continue
        rows.append({
            "code": code,
            "price": last,
            "change": last - prev_close,
            "change_pct": (last / prev_close - 1) * 100,
            "trading_value": last * volume,
            "date": p.index[-1].strftime("%Y-%m-%d"),
        })

    result = pd.DataFrame(rows).merge(companies, on="code")
    # 一番新しい取引日のものだけ（取引停止中の会社を除く）
    result = result[result["date"] == result["date"].max()]
    result = result[result["trading_value"] >= min_trading_value]
    return result.sort_values("change_pct", ascending=False).head(top_n).reset_index(drop=True)


def _download_prices(tickers: list[str], chunk: int = 300, retries: int = 4) -> dict[str, pd.DataFrame]:
    """一度にたくさん頼むと断られるので、小分けにして取得する。断られた分は少し待ってやり直す。"""
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    result: dict[str, pd.DataFrame] = {}
    pending = list(tickers)
    for attempt in range(retries):
        failed = []
        for i in range(0, len(pending), chunk):
            part = pending[i:i + chunk]
            data = yf.download(
                part, period="5d", interval="1d", group_by="ticker",
                auto_adjust=False, threads=True, progress=False,
            )
            for t in part:
                if t in data.columns.get_level_values(0):
                    p = data[t].dropna(subset=["Close"])
                    if len(p):
                        result[t] = p
                        continue
                failed.append(t)
            time.sleep(2)
        if not failed:
            break
        pending = failed
        time.sleep(10 * (attempt + 1))
    return result


def save_snapshot(df: pd.DataFrame, timing: str) -> Path:
    """取得した結果を、あとから見返せるように保存する。"""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(JST)
    path = SNAPSHOT_DIR / f"{now:%Y-%m-%d_%H%M}_{timing}.json"
    payload = {
        "taken_at": now.isoformat(timespec="minutes"),
        "timing": timing,
        "rows": df.to_dict(orient="records"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def list_snapshots() -> list[dict]:
    """保存済みの結果を新しい順に返す。"""
    if not SNAPSHOT_DIR.exists():
        return []
    items = []
    for f in sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True):
        data = json.loads(f.read_text(encoding="utf-8-sig"))
        data["file"] = f.name
        items.append(data)
    return items


if __name__ == "__main__":
    import sys

    timing = sys.argv[1] if len(sys.argv) > 1 else "manual"
    top = fetch_top_gainers()
    print(top[["code", "name", "sector", "price", "change_pct"]].to_string())
    print("保存先:", save_snapshot(top, timing))
