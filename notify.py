"""Discord へお知らせを送る。

送り先（Webhook URL）は環境変数 DISCORD_WEBHOOK_URL から読む。
設定されていないときは送らずに、送る予定の中身を画面に出すだけにする。
"""

import os

import pandas as pd
import requests

import company_info


def build_message(df: pd.DataFrame, title: str, metrics: dict[str, dict] | None = None) -> dict:
    """上位10社を業種ごとにまとめた、Discord に送る中身を作る。

    metrics: 会社コードごとの指標（company_info.fetch_metrics の結果）。あれば2行目に載せる。
    """
    metrics = metrics or {}
    df = df.copy()
    df["rank"] = range(1, len(df) + 1)
    lines = []
    # 一番順位の高い会社がいる業種から順に並べる
    order = df.groupby("sector")["rank"].min().sort_values().index
    for sector in order:
        part = df[df["sector"] == sector]
        lines.append(f"**■ {sector}（{len(part)}社）**")
        for r in part.itertuples():
            # 会社名を押すと株探のページ（ニュースや詳しい情報）が開く
            lines.append(
                f"{r.rank}. [{r.name}（{r.code}）]({company_info.kabutan_url(r.code)})"
                f" **+{r.change_pct:.1f}%**　{r.price:,.0f}円"
            )
            if r.code in metrics:
                lines.append(f"　{company_info.summary_line(metrics[r.code])}")
        lines.append("")
    return {
        "embeds": [{
            "title": title,
            "description": "\n".join(lines).strip(),
            "color": 0x2E9E5B,
            "footer": {"text": "株価は約20分遅れ（Yahoo Finance）"},
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
            "title": "📰 上位10社の最新ニュース",
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
