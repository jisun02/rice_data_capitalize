from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import db as db_layer


st.set_page_config(
    page_title="쌀 무역 인텔리전스 대시보드",
    layout="wide",
)


TRADER_OPTIONS = ["지선", "민지", "현우", "기타"]
ORIGIN_OPTIONS = ["태국", "베트남", "인도", "파키스탄", "미국", "기타"]
RICE_TYPE_OPTIONS = ["백미 5%", "백미 25%", "자스민", "파보일드", "기타"]
PACKAGING_OPTIONS = ["50kg PP백", "1MT 점보백", "벌크", "기타"]
INCOTERM_OPTIONS = ["FOB", "EXW", "FAS", "CFR", "CIF"]

ORIGIN_PORT_OPTIONS = ["방콕", "호치민", "칸들라", "카라치", "휴스턴", "기타"]
DESTINATION_PORT_OPTIONS = ["부산", "인천", "상하이", "홍콩", "싱가포르", "기타"]
SHIPPING_LINE_OPTIONS = ["Maersk", "MSC", "CMA CGM", "ONE", "Hapag-Lloyd", "기타"]


@st.cache_resource
def get_conn():
    conn = db_layer.connect()
    db_layer.init_db(conn)
    return conn


def _to_iso(d: date) -> str:
    return d.isoformat()


def load_market_df(conn) -> pd.DataFrame:
    rows = db_layer.fetch_df(
        conn,
        """
        SELECT
            id, offer_date, valid_from, valid_to,
            trader_name, origin, rice_type, packaging, incoterm,
            fob_price, conditions
        FROM market_offers
        ORDER BY offer_date ASC, id ASC;
        """,
    )
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    for col in ["offer_date", "valid_from", "valid_to"]:
        df[col] = pd.to_datetime(df[col]).dt.date
    return df


def load_freight_df(conn) -> pd.DataFrame:
    rows = db_layer.fetch_df(
        conn,
        """
        SELECT
            id, offer_date, valid_from, valid_to,
            trader_name, origin_port, destination_port, shipping_line,
            freight_cost, conditions
        FROM freight_offers
        ORDER BY offer_date ASC, id ASC;
        """,
    )
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    for col in ["offer_date", "valid_from", "valid_to"]:
        df[col] = pd.to_datetime(df[col]).dt.date
    return df


def apply_common_filters(df: pd.DataFrame, *, offer_range: tuple[date, date], valid_range: tuple[date, date]) -> pd.DataFrame:
    if df.empty:
        return df
    od_start, od_end = offer_range
    vd_start, vd_end = valid_range
    out = df.copy()
    out = out[(out["offer_date"] >= od_start) & (out["offer_date"] <= od_end)]
    out = out[(out["valid_from"] <= vd_end) & (out["valid_to"] >= vd_start)]
    return out


conn = get_conn()

tab_dashboard, tab_market_entry, tab_freight_entry = st.tabs(
    ["대시보드", "쌀 오퍼 등록", "해상 운임 등록"]
)


with tab_dashboard:
    st.subheader("대시보드")

    market_df = load_market_df(conn)
    freight_df = load_freight_df(conn)

    today = date.today()

    # 기본 기간: 최근 180일
    default_offer_start = today.replace(day=1)
    default_offer_end = today

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        offer_date_range = st.date_input(
            "오퍼 접수일 범위",
            value=(default_offer_start, default_offer_end),
        )
    with col2:
        valid_date_range = st.date_input(
            "유효기간(Valid) 범위",
            value=(default_offer_start, default_offer_end),
        )

    # date_input returns date or tuple depending on streamlit version/user interaction
    if isinstance(offer_date_range, tuple):
        offer_start, offer_end = offer_date_range
    else:
        offer_start, offer_end = offer_date_range, offer_date_range

    if isinstance(valid_date_range, tuple):
        valid_start, valid_end = valid_date_range
    else:
        valid_start, valid_end = valid_date_range, valid_date_range

    st.divider()
    st.markdown("#### 쌀 오퍼 필터")
    mcol1, mcol2, mcol3 = st.columns(3)
    with mcol1:
        origin_sel = st.multiselect("원산지", ORIGIN_OPTIONS, default=[])
    with mcol2:
        rice_type_sel = st.multiselect("쌀 품종", RICE_TYPE_OPTIONS, default=[])
    with mcol3:
        packaging_sel = st.multiselect("포장 형태", PACKAGING_OPTIONS, default=[])

    st.markdown("#### 운임 오퍼 필터")
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        origin_port_sel = st.multiselect("출발항", ORIGIN_PORT_OPTIONS, default=[])
    with fcol2:
        destination_port_sel = st.multiselect("도착항", DESTINATION_PORT_OPTIONS, default=[])
    with fcol3:
        shipping_line_sel = st.multiselect("선사", SHIPPING_LINE_OPTIONS, default=[])

    st.divider()

    filtered_market = apply_common_filters(
        market_df,
        offer_range=(offer_start, offer_end),
        valid_range=(valid_start, valid_end),
    )
    if not filtered_market.empty:
        if origin_sel:
            filtered_market = filtered_market[filtered_market["origin"].isin(origin_sel)]
        if rice_type_sel:
            filtered_market = filtered_market[filtered_market["rice_type"].isin(rice_type_sel)]
        if packaging_sel:
            filtered_market = filtered_market[filtered_market["packaging"].isin(packaging_sel)]

    filtered_freight = apply_common_filters(
        freight_df,
        offer_range=(offer_start, offer_end),
        valid_range=(valid_start, valid_end),
    )
    if not filtered_freight.empty:
        if origin_port_sel:
            filtered_freight = filtered_freight[filtered_freight["origin_port"].isin(origin_port_sel)]
        if destination_port_sel:
            filtered_freight = filtered_freight[filtered_freight["destination_port"].isin(destination_port_sel)]
        if shipping_line_sel:
            filtered_freight = filtered_freight[filtered_freight["shipping_line"].isin(shipping_line_sel)]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 쌀 가격 추이 (FOB, MT당)")
        if filtered_market.empty:
            st.info("조건에 맞는 쌀 오퍼 데이터가 없습니다.")
        else:
            filtered_market = filtered_market.copy()
            filtered_market["구분"] = (
                filtered_market["origin"].astype(str)
                + " / "
                + filtered_market["rice_type"].astype(str)
                + " / "
                + filtered_market["packaging"].astype(str)
            )
            fig = px.line(
                filtered_market,
                x="offer_date",
                y="fob_price",
                color="구분",
                markers=True,
                hover_data=[
                    "valid_from",
                    "valid_to",
                    "incoterm",
                    "trader_name",
                    "conditions",
                ],
            )
            fig.update_layout(
                xaxis_title="오퍼 접수일",
                yaxis_title="FOB 가격",
                legend_title_text="조건",
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("#### 해상 운임 추이")
        if filtered_freight.empty:
            st.info("조건에 맞는 운임 오퍼 데이터가 없습니다.")
        else:
            filtered_freight = filtered_freight.copy()
            filtered_freight["구분"] = (
                filtered_freight["origin_port"].astype(str)
                + " → "
                + filtered_freight["destination_port"].astype(str)
                + " / "
                + filtered_freight["shipping_line"].astype(str)
            )
            fig = px.line(
                filtered_freight,
                x="offer_date",
                y="freight_cost",
                color="구분",
                markers=True,
                hover_data=[
                    "valid_from",
                    "valid_to",
                    "trader_name",
                    "conditions",
                ],
            )
            fig.update_layout(
                xaxis_title="오퍼 접수일",
                yaxis_title="운임",
                legend_title_text="조건",
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("#### 필터링된 원본 데이터")

    dt1, dt2 = st.tabs(["쌀 오퍼 원본", "운임 오퍼 원본"])
    with dt1:
        if filtered_market.empty:
            st.write("표시할 데이터가 없습니다.")
        else:
            st.dataframe(
                filtered_market,
                use_container_width=True,
                hide_index=True,
            )
    with dt2:
        if filtered_freight.empty:
            st.write("표시할 데이터가 없습니다.")
        else:
            st.dataframe(
                filtered_freight,
                use_container_width=True,
                hide_index=True,
            )


with tab_market_entry:
    st.subheader("쌀 오퍼 등록")
    st.caption("날짜/가격/메모를 제외한 항목은 드롭다운에서 선택해주세요.")

    with st.form("market_offer_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            offer_date = st.date_input("오퍼 접수일", value=date.today())
        with c2:
            valid_from = st.date_input("유효 시작일", value=date.today())
        with c3:
            valid_to = st.date_input("유효 종료일", value=date.today())
        with c4:
            trader_name = st.selectbox("담당자", TRADER_OPTIONS, index=0)

        c5, c6, c7, c8 = st.columns(4)
        with c5:
            origin = st.selectbox("원산지", ORIGIN_OPTIONS, index=0)
        with c6:
            rice_type = st.selectbox("쌀 품종", RICE_TYPE_OPTIONS, index=0)
        with c7:
            packaging = st.selectbox("포장 형태", PACKAGING_OPTIONS, index=0)
        with c8:
            incoterm = st.selectbox("인코텀즈", INCOTERM_OPTIONS, index=0)

        c9, c10 = st.columns([1, 2])
        with c9:
            fob_price = st.number_input("FOB 가격 (MT당)", min_value=0.0, value=0.0, step=1.0)
        with c10:
            conditions = st.text_area("기타 조건/메모", height=120, placeholder="선적 기간 등")

        submitted = st.form_submit_button("저장")

    if submitted:
        if valid_from > valid_to:
            st.error("유효 시작일은 유효 종료일보다 늦을 수 없습니다.")
        else:
            new_id = db_layer.insert_market_offer(
                conn,
                {
                    "offer_date": _to_iso(offer_date),
                    "valid_from": _to_iso(valid_from),
                    "valid_to": _to_iso(valid_to),
                    "trader_name": trader_name,
                    "origin": origin,
                    "rice_type": rice_type,
                    "packaging": packaging,
                    "incoterm": incoterm,
                    "fob_price": float(fob_price),
                    "conditions": conditions,
                },
            )
            st.success(f"저장 완료! (ID: {new_id})")


with tab_freight_entry:
    st.subheader("해상 운임 등록")
    st.caption("날짜/운임/메모를 제외한 항목은 드롭다운에서 선택해주세요.")

    with st.form("freight_offer_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            offer_date = st.date_input("오퍼 접수일", value=date.today(), key="f_offer_date")
        with c2:
            valid_from = st.date_input("유효 시작일", value=date.today(), key="f_valid_from")
        with c3:
            valid_to = st.date_input("유효 종료일", value=date.today(), key="f_valid_to")
        with c4:
            trader_name = st.selectbox("담당자", TRADER_OPTIONS, index=0, key="f_trader")

        c5, c6, c7 = st.columns(3)
        with c5:
            origin_port = st.selectbox("출발항", ORIGIN_PORT_OPTIONS, index=0)
        with c6:
            destination_port = st.selectbox("도착항", DESTINATION_PORT_OPTIONS, index=0)
        with c7:
            shipping_line = st.selectbox("선사", SHIPPING_LINE_OPTIONS, index=0)

        c8, c9 = st.columns([1, 2])
        with c8:
            freight_cost = st.number_input("운임", min_value=0.0, value=0.0, step=1.0)
        with c9:
            conditions = st.text_area("기타 조건/메모", height=120, placeholder="환적 여부, Free time 등")

        submitted = st.form_submit_button("저장")

    if submitted:
        if valid_from > valid_to:
            st.error("유효 시작일은 유효 종료일보다 늦을 수 없습니다.")
        else:
            new_id = db_layer.insert_freight_offer(
                conn,
                {
                    "offer_date": _to_iso(offer_date),
                    "valid_from": _to_iso(valid_from),
                    "valid_to": _to_iso(valid_to),
                    "trader_name": trader_name,
                    "origin_port": origin_port,
                    "destination_port": destination_port,
                    "shipping_line": shipping_line,
                    "freight_cost": float(freight_cost),
                    "conditions": conditions,
                },
            )
            st.success(f"저장 완료! (ID: {new_id})")

