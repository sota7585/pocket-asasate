"""決まった時間に自動で動かすための入口。

使い方: python scheduled_run.py <区切り>
  区切り: morning（朝のまとめ） / open_am / close_am / open_pm / close_pm / manual
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import company_info
import morning
import notify
import ranking


DETAIL_WORKERS = 6   # 同時に情報を集める社数（多すぎると取得元に断られる）


def log(text: str) -> None:
    """どこまで進んだかを、時刻つきですぐに出す（時間がかかっている所を見つけるため）。"""
    print(f"[{datetime.now(ranking.JST):%H:%M:%S}] {text}", flush=True)


def collect_detail(r) -> dict:
    """1社ぶんの指標とニュース5件。取れなかったものは空のまま返す（1社取れなくても全体は止めない）。"""
    d = {"metrics": None, "news": []}
    try:
        d["metrics"] = company_info.fetch_metrics(r.code)
    except Exception as e:
        print(f"{r.code} の指標が取れませんでした: {e}")
    try:
        d["news"] = company_info.fetch_news(r.name, limit=5, code=r.code)
    except Exception as e:
        print(f"{r.code} のニュースが取れませんでした: {e}")
    return d


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

    # アプリで「売買代金で絞る」ができるよう、多めに記録しておく
    log("全社の株価を集めはじめます")
    top_all = ranking.fetch_top_gainers(top_n=ranking.KEEP_ROWS)
    log("全社の株価を集めおわりました")
    if top_all.empty:
        print("株価が取れませんでした")
        sys.exit(1)

    # 一番新しい株価が今日のものでなければ、取引所が休みの日
    if top_all["date"].iloc[0] != now.strftime("%Y-%m-%d") and timing != "manual":
        print(f"今日（{now:%m/%d}）は取引がないため、お知らせしません")
        return

    top = top_all.head(10)   # Discord は文字数の上限があるので10社
    # 絞り方ごとの上位100社すべてについて、指標とニュース5件を集めて記録に入れる（アプリで会社を押したとき用）
    # 社数が多いので、何社かずつ並行して集める
    targets = list(ranking.detail_targets(top_all).itertuples())
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        details = dict(zip((r.code for r in targets), pool.map(collect_detail, targets)))
    log(f"{len(details)} 社の詳しい情報を集めました")
    ranking.save_snapshot(top_all, timing, details)
    removed = ranking.prune_snapshots()
    if removed:
        print(f"{ranking.KEEP_DAYS}日より前の記録を {removed} 件消しました")

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
