"""値上がり上位の会社を業種ごとに見るページ。"""

from datetime import datetime

import pandas as pd
import streamlit as st

import company_info
import ranking


def guess_timing(now: datetime) -> str:
    """今の時刻から、どの区切りの記録かを決める。"""
    hm = now.hour * 100 + now.minute
    if 900 <= hm < 1130:
        return "open_am"
    if 1130 <= hm < 1230:
        return "close_am"
    if 1230 <= hm < 1530:
        return "open_pm"
    if hm >= 1530:
        return "close_pm"
    return "manual"


@st.cache_data(ttl=3600, max_entries=200, show_spinner=False)
def load_metrics(code: str) -> dict:
    return company_info.fetch_metrics(code)


@st.cache_data(ttl=900, max_entries=200, show_spinner=False)
def load_news(name: str, code: str) -> list[dict]:
    return company_info.fetch_news(name, code=code)


@st.dialog("会社の詳しい情報", width="medium")
def show_details(code: str, name: str) -> None:
    st.subheader(f"{name}　:gray[{code}]")
    with st.spinner("情報を集めています…"):
        m = load_metrics(code)
        news = load_news(name, code)

    with st.container(horizontal=True):
        st.metric("PER（株価が利益の何倍か）", company_info.fmt_times(m["per"]), border=True)
        st.metric("PBR（株価が純資産の何倍か）", company_info.fmt_times(m["pbr"]), border=True)
    with st.container(horizontal=True):
        st.metric("時価総額", company_info.fmt_yen(m["market_cap"]), border=True)
        st.metric("ROE（自己資本でどれだけ稼いだか）", company_info.fmt_pct(m["roe"]), border=True)
    with st.container(horizontal=True):
        st.metric("有利子負債（借金）", company_info.fmt_yen(m["debt"]), border=True)
        st.metric(
            "ネットキャッシュ比率", company_info.fmt_ratio(m["net_cash_ratio"]), border=True,
            help="（流動資産＋投資有価証券×0.7−負債合計）÷時価総額。1を超えると、時価総額より実質的なお金が多い",
        )
    st.caption("指標は Yahoo Finance の数字です。銀行など一部の業種では、ネットキャッシュ比率は出ません。")

    st.markdown("#### ニュース")
    if not news:
        st.write("ニュースが見つかりませんでした。")
    for n in news:
        when = datetime.fromisoformat(n["published"]).strftime("%m/%d %H:%M") if n["published"] else ""
        st.markdown(f"[{n['title']}]({n['link']})  \n:gray[{when}・{n['source']}]")

    st.link_button("株探で見る", company_info.kabutan_url(code), icon=":material/open_in_new:", width="stretch")


def snapshot_label(s: dict) -> str:
    taken = datetime.fromisoformat(s["taken_at"])
    return f"{taken:%m/%d %H:%M}　{ranking.TIMINGS.get(s['timing'], s['timing'])}"


st.title(f"値上がり上位{ranking.TOP_N}社")
st.caption(f"東証の全上場株から、前の日の終値より上がった割合が大きい順に{ranking.TOP_N}社。株価は約20分遅れです。")

with st.expander("最新の情報を取りに行く", icon=":material/refresh:"):
    st.write("全社（約3,700社）の株価を集めるので、4〜5分かかります。")
    min_value = st.select_slider(
        "売買代金がこれより少ない会社は除く",
        options=[0, 10_000_000, 100_000_000, 1_000_000_000],
        format_func=lambda v: "除かない" if v == 0 else f"{v // 100_000_000}億円" if v >= 100_000_000 else f"{v // 10_000}万円",
    )
    if st.button("今すぐ取得する", icon=":material/download:", type="primary", width="stretch"):
        with st.spinner("株価を集めています…"):
            top = ranking.fetch_top_gainers(top_n=ranking.TOP_N, min_trading_value=min_value)
            ranking.save_snapshot(top, guess_timing(datetime.now(ranking.JST)))
        st.success("取得しました")

snapshots = ranking.list_snapshots()
if not snapshots:
    st.info("まだ記録がありません。上の「最新の情報を取りに行く」から取得してください。")
    st.stop()

chosen = st.selectbox(
    "どの回を見るか",
    range(len(snapshots)),
    format_func=lambda i: snapshot_label(snapshots[i]),
)
# 記録には多めに入っているので、先頭の TOP_N 社だけを使う
df = pd.DataFrame(snapshots[chosen]["rows"]).head(ranking.TOP_N)
df.insert(0, "rank", range(1, len(df) + 1))

# 業種ごとのまとめ（上位に多い業種が分かるように）
counts = df["sector"].value_counts()
st.subheader("業種の内訳")
st.bar_chart(counts, horizontal=True, x_label="", y_label="社数", height=70 + 40 * len(counts), alt="上位の会社の業種ごとの社数")

st.subheader("業種ごとの一覧")
# 一番順位の高い会社がいる業種から順に並べる
order = df.groupby("sector")["rank"].min().sort_values().index
for sector in order:
    part = df[df["sector"] == sector]
    with st.container(border=True):
        st.markdown(f"#### {sector}　:gray[{len(part)}社]")
        # スマホでも横にはみ出さないよう、1社を2行で表示する。会社名を押すと詳しい情報が出る
        for r in part.itertuples():
            if st.button(
                f"**{r.rank}位　{r.name}**　:green[**+{r.change_pct:.1f}%**]",
                key=f"detail_{chosen}_{r.code}",
                type="tertiary",
                help="押すと詳しい情報を表示",
            ):
                show_details(r.code, r.name)
            st.caption(f"{r.code}・{r.market}・{r.price:,.0f}円（+{r.change:,.0f}円）")
