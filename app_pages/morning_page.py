"""朝のまとめ（モーニングサテライトの代わり）のページ。"""

from datetime import datetime

import streamlit as st

import company_info
import morning

st.title("朝のまとめ")

summary = morning.load_latest()

with st.expander("今の情報で作り直す", icon=":material/refresh:"):
    st.write("毎朝7時に自動で作られます。今の情報で見たいときに押してください（30秒ほど）。")
    if st.button("作り直す", icon=":material/autorenew:", type="primary", width="stretch"):
        with st.spinner("情報を集めています…"):
            summary = morning.build_summary()
            morning.save_summary(summary)

if not summary:
    st.info("まだ朝のまとめがありません。上の「今の情報で作り直す」から作ってください。")
    st.stop()

created = datetime.fromisoformat(summary["created_at"])
st.caption(f"{created:%m月%d日 %H:%M} 時点")

st.subheader("今日の始まりの目安")
with st.container(border=True):
    st.markdown(morning.outlook_text(summary["outlook"]))
    st.caption("日経平均先物（シカゴ・円建て）と、前の日の日経平均の差から出した目安です。")


def quote_metrics(rows: list[dict]) -> None:
    # スマホでも数字が切れないよう、1つを1行で表示する（上がったら緑、下がったら赤）
    with st.container(border=True):
        for r in rows:
            d = r["digits"]
            color = "green" if r["change"] >= 0 else "red"
            st.markdown(
                f"{r['label']}　**{r['value']:,.{d}f}{r['unit']}**　"
                f":{color}[{r['change']:+,.{d}f}（{r['change_pct']:+.1f}%）]"
            )


st.subheader("アメリカの市場（前日の終値）")
quote_metrics(summary["us_market"])

st.subheader("為替・原油・金・金利")
quote_metrics(summary["others"])

st.subheader("前日の値上がり上位10社")
prev = summary["previous_top"]
if not prev:
    st.write("前日の「後場の終わり」の記録がありません。")
else:
    with st.container(border=True):
        for i, r in enumerate(prev["rows"], 1):
            st.markdown(
                f"**{i}位　[{r['name']}]({company_info.kabutan_url(r['code'])})**"
                f"　:green[**+{r['change_pct']:.1f}%**]  \n:gray[{r['sector']}・{r['price']:,.0f}円]"
            )

st.subheader("ニュース")
for group in summary["news"]:
    with st.container(border=True):
        st.markdown(f"**{group['label']}**")
        for n in group["items"]:
            when = datetime.fromisoformat(n["published"]).strftime("%m/%d %H:%M") if n["published"] else ""
            st.markdown(f"[{n['title']}]({n['link']})  \n:gray[{when}・{n['source']}]")
