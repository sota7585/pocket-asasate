"""Discord へお知らせを送る。

送り先（Webhook URL）は環境変数 DISCORD_WEBHOOK_URL から読む。
設定されていないときは送らずに、送る予定の中身を画面に出すだけにする。
"""

import os

import pandas as pd
import requests


def build_message(df: pd.DataFrame, title: str) -> dict:
    """上位10社を業種ごとにまとめた、Discord に送る中身を作る。"""
    df = df.copy()
    df["rank"] = range(1, len(df) + 1)
    lines = []
    # 一番順位の高い会社がいる業種から順に並べる
    order = df.groupby("sector")["rank"].min().sort_values().index
    for sector in order:
        part = df[df["sector"] == sector]
        lines.append(f"**■ {sector}（{len(part)}社）**")
        for r in part.itertuples():
            lines.append(
                f"{r.rank}. {r.name}（{r.code}） **+{r.change_pct:.1f}%**　{r.price:,.0f}円"
            )
        lines.append("")
    return {
        "embeds": [{
            "title": title,
            "description": "\n".join(lines).strip(),
            "color": 0x2E9E5B,
            "footer": {"text": "株価は約20分遅れ（Yahoo Finance）"},
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
