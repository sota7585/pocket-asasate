"""決まった時間に自動で動かすための入口。

使い方: python scheduled_run.py <区切り>
  区切り: open_am / close_am / open_pm / close_pm / manual
"""

import sys
from datetime import datetime

import company_info
import notify
import ranking


def main(timing: str) -> None:
    now = datetime.now(ranking.JST)
    # 月が変わったら会社の一覧を取り直す（新しく上場した会社を入れるため）
    if not ranking.LIST_FILE.exists() or now.day <= 7:
        ranking.update_company_list()

    top = ranking.fetch_top_gainers()
    if top.empty:
        print("株価が取れませんでした")
        sys.exit(1)

    # 一番新しい株価が今日のものでなければ、取引所が休みの日
    if top["date"].iloc[0] != now.strftime("%Y-%m-%d") and timing != "manual":
        print(f"今日（{now:%m/%d}）は取引がないため、お知らせしません")
        return

    ranking.save_snapshot(top, timing)
    metrics = {}
    for code in top["code"]:
        try:
            metrics[code] = company_info.fetch_metrics(code)
        except Exception as e:  # 1社取れなくても、お知らせ自体は送る
            print(f"{code} の指標が取れませんでした: {e}")
    title = f"【{ranking.TIMINGS[timing]}】値上がり上位10社　{now:%m/%d %H:%M}"
    if notify.send(notify.build_message(top, title, metrics)):
        print("Discord に送りました")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "manual")
