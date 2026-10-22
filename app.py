"""ポケット朝サテ＋速報便の画面（入口）。

起動: .venv\\Scripts\\streamlit run app.py
"""

from datetime import datetime

import streamlit as st

import ranking

st.set_page_config(page_title="ポケット朝サテ", page_icon=":material/trending_up:", layout="centered")

# 朝（取引が始まる9時より前）は朝のまとめを、それ以外は値上がり上位を最初に出す
is_morning = datetime.now(ranking.JST).hour < 9

page = st.navigation(
    [
        st.Page("app_pages/morning_page.py", title="朝のまとめ", icon=":material/wb_twilight:", default=is_morning),
        st.Page("app_pages/ranking_page.py", title="値上がり上位", icon=":material/trending_up:", default=not is_morning),
    ],
    position="top",
)
page.run()
