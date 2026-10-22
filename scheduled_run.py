"""決まった時間に自動で動かすための入口。

使い方: python scheduled_run.py <区切り>
  区切り: morning（朝のまとめ） / open_am / close_am / open_pm / close_pm / manual
"""

import sys
from datetime import datetime

import company_info
import morning
import notify
import ranking


def run_morning() -> None:
    summary = morning.build_summary()
    morning.save_summary(summary)
    sent = [notify.send(p) for p in morning.build_messages(summary)]
    if all(sent):
        print("Discord に朝のまとめを送りました")


def main(timing: str) -> None:
    if timing == "morning":
        run_morning()
        return

    now = datetime.now(ranking.JST)
    # 月が変わったら会社の一覧を取り直す（新しく上場した会社を入れるため）
    if not ranking.LIST_FILE.exists() or now.day <= 7:
        ranking.update_company_list()

    # ページで「売買代金で絞る」ができるよう、上位50社まで記録しておく
    top_all = ranking.fetch_top_gainers(top_n=ranking.KEEP_ROWS)
    if top_all.empty:
        print("株価が取れませんでした")
        sys.exit(1)

    # 一番新しい株価が今日のものでなければ、取引所が休みの日
    if top_all["date"].iloc[0] != now.strftime("%Y-%m-%d") and timing != "manual":
        print(f"今日（{now:%m/%d}）は取引がないため、お知らせしません")
        return

    top = top_all.head(10)
    # 絞り方ごとの上位10社すべてについて、指標とニュース5件を集めて記録に入れる（ページで会社を押したとき用）
    details = {}
    for r in ranking.detail_targets(top_all).itertuples():
        d = {"metrics": None, "news": []}
        try:
            d["metrics"] = company_info.fetch_metrics(r.code)
        except Exception as e:  # 1社取れなくても、お知らせ自体は送る
            print(f"{r.code} の指標が取れませんでした: {e}")
        d["news"] = company_info.fetch_news(r.name, limit=5, code=r.code)
        details[r.code] = d
    ranking.save_snapshot(top_all, timing, details)

    metrics = {c: d["metrics"] for c, d in details.items() if d["metrics"]}
    news = {c: d["news"][:1] for c, d in details.items()}
    # 「前場の終わり（11:30）」→「前場の終わり」。時刻はタイトルの最後に付く
    label = ranking.TIMINGS[timing].split("（")[0]
    title = f"{label}　上位10社　{now:%m/%d %H:%M}"
    if notify.send(notify.build_message(top, title, metrics)):
        print("Discord に送りました")
    news_payload = notify.build_news_message(top, news)
    if news_payload:
        notify.send(news_payload)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "manual")
