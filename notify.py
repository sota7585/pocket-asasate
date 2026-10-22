"""Discord へお知らせを送る。

送り先（Webhook URL）は環境変数 DISCORD_WEBHOOK_URL から読む。
設定されていないときは送らずに、送る予定の中身を画面に出すだけにする。
"""

import os

import pandas as pd
import requests

import company_info

# メインのアプリ（GitHub Pages）。お知らせのタイトルを押すと開く
APP_URL = "https://sota7585.github.io/pocket-asasate/"


def short_sector(sector: str) -> str:
    """業種の札に使う短い名前。「情報・通信業」→「情報・通信」。「鉱業」のような2文字はそのまま。"""
    return sector[:-1] if sector.endswith("業") and len(sector) > 2 else sector


def sector_summary(df: pd.DataFrame) -> str:
    """「業種：**情報・通信 8**｜卸売 1｜サービス 1」の1行。一番多い業種を太字にする。"""
    counts = df["sector"].value_counts()   # 多い順
    parts = [f"{short_sector(s)} {n}" for s, n in counts.items()]
    parts[0] = f"**{parts[0]}**"
    return "業種：" + "｜".join(parts)


def build_message(df: pd.DataFrame, title: str, metrics: dict[str, dict] | None = None) -> dict:
    """上位10社のお知らせ（デザイン案B：数字が先・順位どおり・業種は札）を作る。

    metrics: 会社コードごとの指標（company_info.fetch_metrics の結果）。あれば各社の2行目に載せる。
    """
    metrics = metrics or {}
    lines = [sector_summary(df), ""]
    for rank, r in enumerate(df.itertuples(), 1):
        # 会社名を押すと株探のページ（ニュースや詳しい情報）が開く。1位だけ会社名を太字にする
        name = f"[{r.name}]({company_info.kabutan_url(r.code)})"
        if rank == 1:
            name = f"**{name}**"
        lines.append(f"{rank}　**+{r.change_pct:.1f}%**　{name}　`{short_sector(r.sector)}`")
        if r.code in metrics:
            lines.append(f"　　{company_info.summary_line(metrics[r.code])}")
    return {
        "embeds": [{
            "title": title,
            "url": APP_URL,
            "description": "\n".join(lines),
            "color": 0x57F287,
            "footer": {"text": "株価は約20分遅れ｜タイトルを押すとアプリ、会社名を押すと株探が開きます"},
        }]
    }


def build_news_message(df: pd.DataFrame, news: dict[str, list[dict]]) -> dict | None:
    """上位10社それぞれの最新ニュースを1件ずつ載せた、2通目の中身を作る。

    ニュースのリンクは長いので、1通目に入れると文字数の上限を超える。そのため分けて送る。
    """
    lines = []
    for i, r in enumerate(df.itertuples(), 1):
        items = news.get(r.code) or []
        if not items:
            lines.append(f"{i}. **{r.name}**\n　（ニュースなし）")
            continue
        n = items[0]
        lines.append(f"{i}. **{r.name}**\n　[{n['title'][:50]}]({n['link']})")
    if not lines:
        return None
    # 文字数の上限（4096字）を超えないところまで載せる。リンクの途中では切らない
    kept, total = [], 0
    for line in lines:
        if total + len(line) + 1 > 4000:
            break
        kept.append(line)
        total += len(line) + 1
    return {
        "embeds": [{
            "title": "上位10社の最新ニュース",
            "url": APP_URL,
            "description": "\n".join(kept),
            "color": 0x777777,
        }]
    }


def send(payload: dict) -> bool:
    """送れたら True。送り先が設定されていなければ中身を表示して False。"""
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("（DISCORD_WEBHOOK_URL が未設定のため送りません。送る予定の中身↓）")
        for e in payload["embeds"]:
            print(e["title"])
            print(e["description"])
        return False
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return True
