from __future__ import annotations

import io
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# 페이지 기본 설정
st.set_page_config(page_title="POSCOINTL RICE OFFER", layout="wide")

# --- 구글 시트 연결 (가장 깔끔한 기본 버전) ---
try:
    # Secrets에 형식이 완벽히 맞으면 이 한 줄로 모든 인증이 끝납니다.
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"연결 설정 오류: {e}")
    st.stop()

# --------------------------------------------------

def load_data(worksheet_name):
    try:
        # ttl="0"은 캐시를 쓰지 않고 실시간으로 구글 시트에서 가져오겠다는 뜻입니다.
        return conn.read(worksheet=worksheet_name, ttl="0")
    except Exception:
        # 데이터가 아예 없는 초기 상태라면 빈 데이터프레임을 반환합니다.
        return pd.DataFrame()


def _parse_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")
    return out


def _numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _multiselect_options(df: pd.DataFrame, col: str) -> list:
    if col not in df.columns or df.empty:
        return []
    return sorted(df[col].dropna().astype(str).unique().tolist())


def _apply_filters(
    df: pd.DataFrame,
    date_col: str | None,
    date_from,
    date_to,
    filters: dict[str, list],
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if date_col and date_col in out.columns:
        out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
        if date_from:
            out = out[out[date_col].dt.normalize() >= pd.Timestamp(date_from)]
        if date_to:
            out = out[out[date_col].dt.normalize() <= pd.Timestamp(date_to)]
    for col, selected in filters.items():
        if col in out.columns and selected:
            out = out[out[col].astype(str).isin(selected)]
    return out


def _offer_date_range_default(df: pd.DataFrame) -> tuple:
    today = datetime.now().date()
    if df.empty or "offer_date" not in df.columns:
        return (today, today)
    ts = pd.to_datetime(df["offer_date"], errors="coerce")
    if not ts.notna().any():
        return (today, today)
    start = ts.min()
    if pd.isna(start):
        return (today, today)
    return (start.date(), today)


def _to_excel_bytes(dfs: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, frame in dfs.items():
            safe = sheet_name[:31] if sheet_name else "Sheet1"
            frame.to_excel(writer, index=False, sheet_name=safe)
    buf.seek(0)
    return buf.getvalue()

# --- 드롭다운 옵션 데이터 정의 ---
TRADER_OPTIONS = ["지선", "민지", "현우", "기타"]
SUPPLIER_OPTIONS = ["Olam", "Phoenix", "Wilmar", "Louis Dreyfus", "기타"] # 자주 쓰는 공급선 목록
ORIGIN_OPTIONS = ["태국", "베트남", "인도", "파키스탄", "미국"]
RICE_TYPE_OPTIONS = ["백미 5%", "백미 25%", "자스민", "파보일드", "현미", "찹쌀"]
PACKAGING_OPTIONS = ["50kg PP백", "1MT 점보백", "BOPP 25kg", "25kg PP백", "벌크"]
INCOTERM_OPTIONS = ["FOB", "CFR", "CIF", "EXW", "FAS"]

# 원산지별 출발항 매핑 (수정사항 2 반영)
PORT_MAPPING = {
    "태국": ["Bangkok", "Laem Chabang", "Koh Sichang"],
    "베트남": ["Ho Chi Minh", "Haiphong", "Danang"],
    "인도": ["Kandla", "Kakinada", "Mundra", "Chennai"],
    "파키스탄": ["Karachi", "Port Qasim"],
    "미국": ["Houston", "New Orleans", "Long Beach"]
}
DESTINATION_PORT_OPTIONS = ["부산", "인천", "광양", "울산", "상하이", "싱가포르", "기타"]
SHIPPING_OPTIONS = ["Maersk", "MSC", "CMA CGM", "ONE", "HMM", "기타"]

# --- 세션 상태 초기화 ---
if "market_price_rows" not in st.session_state:
    st.session_state.market_price_rows = [{"packaging": PACKAGING_OPTIONS[0], "price": 0.0}]

st.title("POSCOINTL RICE OFFER")

tab_dashboard, tab_market_entry, tab_freight_entry, tab_export = st.tabs(
    ["📊 대시보드", "🌾 쌀 오퍼 등록", "🚢 해상 운임 등록", "📥 필터 & Excel"]
)

# --- [1. 대시보드 탭] ---
with tab_dashboard:
    st.subheader("실시간 시장·운임 분석")
    m_df_raw = load_data("market")
    f_df_raw = load_data("freight")

    dash_market, dash_freight = st.tabs(["Market offer", "Freight offer"])

    with dash_market:
        if m_df_raw.empty:
            st.info("쌀 오퍼(market) 시트에 데이터가 없습니다.")
        else:
            m_df = _parse_dates(m_df_raw, ["offer_date", "valid_from", "valid_to"])
            if "fob_price" in m_df.columns:
                m_df["fob_price"] = _numeric_series(m_df["fob_price"])

            c1, c2 = st.columns(2)
            with c1:
                st.metric("총 오퍼 행 수", len(m_df))
            with c2:
                if "fob_price" in m_df.columns:
                    st.metric(
                        "FOB 가격 평균 (USD/MT)",
                        f"{m_df['fob_price'].mean():,.2f}"
                        if m_df["fob_price"].notna().any()
                        else "—",
                    )

            st.caption("아래 차트는 확대·팬·범례 토글·호버 정보를 지원합니다.")
            row1 = st.columns(2)
            with row1[0]:
                if "offer_date" in m_df.columns and "fob_price" in m_df.columns:
                    sub = m_df.dropna(subset=["offer_date", "fob_price"])
                    if not sub.empty:
                        color = "origin" if "origin" in sub.columns else None
                        fig = px.scatter(
                            sub,
                            x="offer_date",
                            y="fob_price",
                            color=color,
                            hover_data=[c for c in ["supplier_name", "rice_type", "packaging", "incoterm"] if c in sub.columns],
                            title="접수일별 FOB 가격 (산점도)",
                            labels={"offer_date": "오퍼 접수일", "fob_price": "FOB (USD/MT)"},
                        )
                        fig.update_layout(legend_title_text="원산지" if color else None)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("날짜·가격이 모두 있는 행이 없어 산점도를 그릴 수 없습니다.")
                else:
                    st.info("offer_date 또는 fob_price 컬럼이 없습니다.")

            with row1[1]:
                if "origin" in m_df.columns and "fob_price" in m_df.columns:
                    agg = (
                        m_df.groupby("origin", dropna=False)["fob_price"]
                        .mean()
                        .reset_index()
                        .dropna(subset=["fob_price"])
                    )
                    if not agg.empty:
                        fig2 = px.bar(
                            agg.sort_values("fob_price", ascending=False),
                            x="origin",
                            y="fob_price",
                            title="원산지별 평균 FOB 가격",
                            labels={"origin": "원산지", "fob_price": "평균 FOB (USD/MT)"},
                        )
                        st.plotly_chart(fig2, use_container_width=True)
                    else:
                        st.info("원산지·가격 데이터로 막대 그래프를 그릴 수 없습니다.")
                else:
                    st.info("origin 또는 fob_price 컬럼이 없습니다.")

            row2 = st.columns(2)
            with row2[0]:
                if "supplier_name" in m_df.columns and "fob_price" in m_df.columns:
                    agg_s = (
                        m_df.groupby("supplier_name", dropna=False)["fob_price"]
                        .mean()
                        .reset_index()
                        .dropna(subset=["fob_price"])
                    )
                    if not agg_s.empty:
                        fig3 = px.bar(
                            agg_s.sort_values("fob_price", ascending=True),
                            x="fob_price",
                            y="supplier_name",
                            orientation="h",
                            title="공급선별 평균 FOB 가격",
                            labels={"supplier_name": "공급선", "fob_price": "평균 FOB (USD/MT)"},
                        )
                        st.plotly_chart(fig3, use_container_width=True)
                    else:
                        st.info("공급선·가격 데이터가 부족합니다.")
                else:
                    st.info("supplier_name 또는 fob_price 컬럼이 없습니다.")

            with row2[1]:
                if "packaging" in m_df.columns and "fob_price" in m_df.columns:
                    sub_p = m_df.dropna(subset=["fob_price", "packaging"])
                    if len(sub_p) >= 2:
                        fig4 = px.box(
                            sub_p,
                            x="packaging",
                            y="fob_price",
                            title="포장 형태별 FOB 가격 분포",
                            labels={"packaging": "포장", "fob_price": "FOB (USD/MT)"},
                        )
                        fig4.update_xaxes(tickangle=-30)
                        st.plotly_chart(fig4, use_container_width=True)
                    else:
                        st.info("박스플롯을 그리기 위한 데이터가 부족합니다.")
                else:
                    st.info("packaging 또는 fob_price 컬럼이 없습니다.")

            if "offer_date" in m_df.columns and "fob_price" in m_df.columns:
                line_df = m_df.dropna(subset=["offer_date", "fob_price"]).sort_values("offer_date")
                if not line_df.empty:
                    split = "rice_type" if "rice_type" in line_df.columns else None
                    fig5 = px.line(
                        line_df,
                        x="offer_date",
                        y="fob_price",
                        color=split,
                        markers=True,
                        title="시간축 FOB 가격 추이 (품종별)" if split else "시간축 FOB 가격 추이",
                        labels={"offer_date": "오퍼 접수일", "fob_price": "FOB (USD/MT)"},
                    )
                    st.plotly_chart(fig5, use_container_width=True)

            with st.expander("최근 쌀 오퍼 원본 (15행)"):
                st.dataframe(m_df_raw.tail(15), width="stretch", hide_index=True)

    with dash_freight:
        if f_df_raw.empty:
            st.info("해상 운임(freight) 시트에 데이터가 없습니다.")
        else:
            f_df = _parse_dates(f_df_raw, ["offer_date", "valid_from", "valid_to"])
            if "freight_cost" in f_df.columns:
                f_df["freight_cost"] = _numeric_series(f_df["freight_cost"])

            fc1, fc2 = st.columns(2)
            with fc1:
                st.metric("총 운임 행 수", len(f_df))
            with fc2:
                if "freight_cost" in f_df.columns:
                    st.metric(
                        "운임 평균 (USD/MT)",
                        f"{f_df['freight_cost'].mean():,.2f}"
                        if f_df["freight_cost"].notna().any()
                        else "—",
                    )

            frow1 = st.columns(2)
            with frow1[0]:
                if "offer_date" in f_df.columns and "freight_cost" in f_df.columns:
                    subf = f_df.dropna(subset=["offer_date", "freight_cost"])
                    if not subf.empty:
                        col_ship = "shipping_line" if "shipping_line" in subf.columns else None
                        figf1 = px.scatter(
                            subf,
                            x="offer_date",
                            y="freight_cost",
                            color=col_ship,
                            hover_data=[c for c in ["origin_port", "destination_port", "trader_name"] if c in subf.columns],
                            title="접수일별 해상 운임 (산점도)",
                            labels={"offer_date": "운임 접수일", "freight_cost": "운임 (USD/MT)"},
                        )
                        st.plotly_chart(figf1, use_container_width=True)
                    else:
                        st.info("날짜·운임이 모두 있는 행이 없습니다.")
                else:
                    st.info("offer_date 또는 freight_cost 컬럼이 없습니다.")

            with frow1[1]:
                if "destination_port" in f_df.columns and "freight_cost" in f_df.columns:
                    aggd = (
                        f_df.groupby("destination_port", dropna=False)["freight_cost"]
                        .mean()
                        .reset_index()
                        .dropna(subset=["freight_cost"])
                    )
                    if not aggd.empty:
                        figf2 = px.bar(
                            aggd.sort_values("freight_cost", ascending=False),
                            x="destination_port",
                            y="freight_cost",
                            title="도착항별 평균 운임",
                            labels={"destination_port": "도착항", "freight_cost": "평균 운임 (USD/MT)"},
                        )
                        st.plotly_chart(figf2, use_container_width=True)
                    else:
                        st.info("도착항·운임 데이터가 부족합니다.")
                else:
                    st.info("destination_port 또는 freight_cost 컬럼이 없습니다.")

            frow2 = st.columns(2)
            with frow2[0]:
                if "shipping_line" in f_df.columns and "freight_cost" in f_df.columns:
                    aggl = (
                        f_df.groupby("shipping_line", dropna=False)["freight_cost"]
                        .mean()
                        .reset_index()
                        .dropna(subset=["freight_cost"])
                    )
                    if not aggl.empty:
                        figf3 = px.bar(
                            aggl.sort_values("freight_cost", ascending=True),
                            x="freight_cost",
                            y="shipping_line",
                            orientation="h",
                            title="선사별 평균 운임",
                            labels={"shipping_line": "선사", "freight_cost": "평균 운임 (USD/MT)"},
                        )
                        st.plotly_chart(figf3, use_container_width=True)
                    else:
                        st.info("선사·운임 데이터가 부족합니다.")
                else:
                    st.info("shipping_line 또는 freight_cost 컬럼이 없습니다.")

            with frow2[1]:
                if (
                    "origin_port" in f_df.columns
                    and "destination_port" in f_df.columns
                    and "freight_cost" in f_df.columns
                ):
                    heat = f_df.pivot_table(
                        values="freight_cost",
                        index="origin_port",
                        columns="destination_port",
                        aggfunc="mean",
                    )
                    if not heat.empty and heat.size > 0:
                        figf4 = px.imshow(
                            heat,
                            labels=dict(x="도착항", y="출발항", color="평균 운임 (USD/MT)"),
                            title="출발항–도착항 평균 운임 (히트맵)",
                            aspect="auto",
                            color_continuous_scale="Blues",
                        )
                        st.plotly_chart(figf4, use_container_width=True)
                    else:
                        st.info("히트맵용 집계 데이터가 없습니다.")
                else:
                    st.info("origin_port, destination_port, freight_cost 컬럼이 필요합니다.")

            if "offer_date" in f_df.columns and "freight_cost" in f_df.columns:
                lf = f_df.dropna(subset=["offer_date", "freight_cost"]).sort_values("offer_date")
                if not lf.empty:
                    split2 = "destination_port" if "destination_port" in lf.columns else None
                    figf5 = px.line(
                        lf,
                        x="offer_date",
                        y="freight_cost",
                        color=split2,
                        markers=True,
                        title="시간축 운임 추이 (도착항별)" if split2 else "시간축 운임 추이",
                        labels={"offer_date": "접수일", "freight_cost": "운임 (USD/MT)"},
                    )
                    st.plotly_chart(figf5, use_container_width=True)

            with st.expander("최근 해상 운임 원본 (15행)"):
                st.dataframe(f_df_raw.tail(15), width="stretch", hide_index=True)

# --- [2. 쌀 오퍼 등록 탭] ---
with tab_market_entry:
    st.subheader("신규 쌀 오퍼 입력")
    
    # 수정사항 1: 현재 시간 자동 설정
    now = datetime.now()
    default_valid_from = now
    # 수정사항 2: valid_to 자동 +1일 설정
    default_valid_to = now + timedelta(days=1)

    with st.form("market_form"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            # 수정사항 1: 날짜/시간 자동 입력 (사용자 수정 가능)
            offer_date = st.date_input("오퍼 접수일", value=now)
            trader_name = st.selectbox("담당자(내부)", TRADER_OPTIONS) # 드롭다운
        with col2:
            valid_from = st.datetime_input("유효 시작일시", value=default_valid_from)
            origin = st.selectbox("원산지", ORIGIN_OPTIONS) # 드롭다운
        with col3:
            valid_to = st.datetime_input("유효 종료일시", value=default_valid_to)
            rice_type = st.selectbox("쌀 품종", RICE_TYPE_OPTIONS) # 드롭다운
        with col4:
            supplier_name = st.selectbox("공급선명 (Supplier)", SUPPLIER_OPTIONS) # 드롭다운
            incoterm = st.selectbox("인코텀즈", INCOTERM_OPTIONS) # 드롭다운

        st.divider()
        st.write("📦 **포장별 가격 정보**")
        
        for i in range(len(st.session_state.market_price_rows)):
            pcol1, pcol2 = st.columns([2, 1])
            with pcol1:
                st.session_state.market_price_rows[i]["packaging"] = st.selectbox(
                    f"포장 형태 {i+1}", PACKAGING_OPTIONS, key=f"m_pack_{i}"
                ) # 드롭다운
            with pcol2:
                st.session_state.market_price_rows[i]["price"] = st.number_input(
                    f"FOB 가격(MT) {i+1}", min_value=0.0, step=0.5, key=f"m_price_{i}"
                )
        
        conditions = st.text_area("기타 조건 및 메모")
        
        add_btn = st.form_submit_button("➕ 포장 종류 추가")
        save_btn = st.form_submit_button("💾 데이터 저장")

    if add_btn:
        st.session_state.market_price_rows.append({"packaging": PACKAGING_OPTIONS[0], "price": 0.0})
        st.rerun()

    if save_btn:
        new_rows = []
        for p_item in st.session_state.market_price_rows:
            new_rows.append({
                "offer_date": offer_date.isoformat(),
                "valid_from": valid_from.isoformat(),
                "valid_to": valid_to.isoformat(),
                "trader_name": trader_name,
                "supplier_name": supplier_name,
                "origin": origin,
                "rice_type": rice_type,
                "packaging": p_item["packaging"],
                "incoterm": incoterm,
                "fob_price": p_item["price"],
                "conditions": conditions
            })
        m_df = load_data("market")
        combined_df = pd.concat([m_df, pd.DataFrame(new_rows)], ignore_index=True)
        conn.update(worksheet="market", data=combined_df)
        st.success("저장되었습니다!")
        st.session_state.market_price_rows = [{"packaging": PACKAGING_OPTIONS[0], "price": 0.0}]
        st.rerun()

# --- [3. 해상 운임 등록 탭] ---
with tab_freight_entry:
    st.subheader("신규 해상 운임 입력")
    
    # 원산지에 따른 항구 필터링 (기존 로직 유지)
    selected_origin_for_port = st.selectbox("원산지 선택 (항구 필터링용)", ORIGIN_OPTIONS, key="origin_port_filter")
    available_origin_ports = PORT_MAPPING.get(selected_origin_for_port, ["기타"])

    # 시간 기본값 설정
    now_f = datetime.now()
    
    with st.form("freight_form"):
        col1, col2 = st.columns(2)
        with col1:
            f_offer_date = st.date_input("운임 접수일", value=now_f)
            f_valid_from = st.datetime_input("유효 시작일시", value=now_f, key="f_valid_from")
            origin_port = st.selectbox("출발항 (Origin Port)", available_origin_ports)
            f_line = st.selectbox("선사 (Shipping Line)", SHIPPING_OPTIONS)
            
        with col2:
            f_trader = st.selectbox("담당자(내부)", TRADER_OPTIONS, key="f_trader_sel")
            f_valid_to = st.datetime_input("유효 종료일시", value=now_f + timedelta(days=7), key="f_valid_to") # 보통 운임은 일주일 단위가 많아 7일로 설정
            destination_port = st.selectbox("도착항 (Destination Port)", DESTINATION_PORT_OPTIONS)
            f_cost = st.number_input("운임 비용 (USD/MT)", min_value=0.0, step=1.0)

        f_conditions = st.text_area("운임 조건 및 메모 (Surcharge, Free time 등)", key="f_cond")
        
        f_save = st.form_submit_button("💾 운임 정보 저장")
        
        if f_save:
            # 기존 데이터 불러오기
            f_df = load_data("freight")
            
            # 새 데이터 생성
            f_new = pd.DataFrame([{
                "offer_date": f_offer_date.isoformat(),
                "valid_from": f_valid_from.isoformat(),
                "valid_to": f_valid_to.isoformat(),
                "trader_name": f_trader,
                "origin_port": origin_port,
                "destination_port": destination_port,
                "shipping_line": f_line,
                "freight_cost": f_cost,
                "conditions": f_conditions
            }])
            
            # 데이터 합치기 및 업로드
            try:
                combined_f_df = pd.concat([f_df, f_new], ignore_index=True)
                conn.update(worksheet="freight", data=combined_f_df)
                st.success("해상 운임 정보가 성공적으로 저장되었습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"저장 중 오류가 발생했습니다: {e}")

# --- [4. 필터 & Excel보내기 탭] ---
with tab_export:
    st.subheader("필터 후 Excel 다운로드")
    ex_m = load_data("market")
    ex_f = load_data("freight")

    dataset_choice = st.radio(
        "보낼 데이터",
        ("쌀 오퍼 (market)", "해상 운임 (freight)", "둘 다 (2개 시트)"),
        horizontal=True,
    )

    st.divider()

    if dataset_choice == "쌀 오퍼 (market)":
        if ex_m.empty:
            st.warning("market 시트에 데이터가 없습니다.")
        else:
            dc_m = st.date_input(
                "오퍼 접수일 범위 (offer_date)",
                value=_offer_date_range_default(ex_m),
                key="ex_m_dates",
            )
            if isinstance(dc_m, tuple) and len(dc_m) == 2:
                d_from, d_to = dc_m
            else:
                d_from = d_to = dc_m

            fm = {}
            cols_m = [
                ("trader_name", "담당자"),
                ("supplier_name", "공급선"),
                ("origin", "원산지"),
                ("rice_type", "품종"),
                ("packaging", "포장"),
                ("incoterm", "인코텀즈"),
            ]
            for col, label in cols_m:
                if col in ex_m.columns:
                    opts = _multiselect_options(ex_m, col)
                    if opts:
                        fm[col] = st.multiselect(label, opts, key=f"ex_m_{col}")

            filtered_m = _apply_filters(
                ex_m, "offer_date" if "offer_date" in ex_m.columns else None, d_from, d_to, fm
            )
            st.caption(f"선택 조건에 맞는 행: **{len(filtered_m)}**")
            st.dataframe(filtered_m.head(200), width="stretch", hide_index=True)
            if len(filtered_m) > 200:
                st.caption("미리보기는 최대 200행입니다. 다운로드 파일에는 전체가 포함됩니다.")

            xlsx_m = _to_excel_bytes({"market": filtered_m})
            st.download_button(
                "Excel 다운로드 (.xlsx)",
                data=xlsx_m,
                file_name=f"market_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    elif dataset_choice == "해상 운임 (freight)":
        if ex_f.empty:
            st.warning("freight 시트에 데이터가 없습니다.")
        else:
            dc_f = st.date_input(
                "운임 접수일 범위 (offer_date)",
                value=_offer_date_range_default(ex_f),
                key="ex_f_dates",
            )
            if isinstance(dc_f, tuple) and len(dc_f) == 2:
                df_from, df_to = dc_f
            else:
                df_from = df_to = dc_f

            ff = {}
            cols_f = [
                ("trader_name", "담당자"),
                ("origin_port", "출발항"),
                ("destination_port", "도착항"),
                ("shipping_line", "선사"),
            ]
            for col, label in cols_f:
                if col in ex_f.columns:
                    opts = _multiselect_options(ex_f, col)
                    if opts:
                        ff[col] = st.multiselect(label, opts, key=f"ex_f_{col}")

            filtered_f = _apply_filters(
                ex_f, "offer_date" if "offer_date" in ex_f.columns else None, df_from, df_to, ff
            )
            st.caption(f"선택 조건에 맞는 행: **{len(filtered_f)}**")
            st.dataframe(filtered_f.head(200), width="stretch", hide_index=True)
            if len(filtered_f) > 200:
                st.caption("미리보기는 최대 200행입니다. 다운로드 파일에는 전체가 포함됩니다.")

            xlsx_f = _to_excel_bytes({"freight": filtered_f})
            st.download_button(
                "Excel 다운로드 (.xlsx)",
                data=xlsx_f,
                file_name=f"freight_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**쌀 오퍼 필터**")
            if ex_m.empty:
                st.caption("market 데이터 없음")
                filtered_m2 = ex_m
            else:
                dc_m2 = st.date_input(
                    "Market 접수일 범위",
                    value=_offer_date_range_default(ex_m),
                    key="ex_both_m_dates",
                )
                if isinstance(dc_m2, tuple) and len(dc_m2) == 2:
                    dm_from, dm_to = dc_m2
                else:
                    dm_from = dm_to = dc_m2
                fm2 = {}
                for col, label in [
                    ("trader_name", "담당자"),
                    ("supplier_name", "공급선"),
                    ("origin", "원산지"),
                    ("rice_type", "품종"),
                    ("packaging", "포장"),
                    ("incoterm", "인코텀즈"),
                ]:
                    if col in ex_m.columns:
                        om = _multiselect_options(ex_m, col)
                        if om:
                            fm2[col] = st.multiselect(label, om, key=f"ex_both_m_{col}")
                filtered_m2 = _apply_filters(
                    ex_m, "offer_date" if "offer_date" in ex_m.columns else None, dm_from, dm_to, fm2
                )
                st.caption(f"market 행 수: **{len(filtered_m2)}**")

        with col_b:
            st.markdown("**해상 운임 필터**")
            if ex_f.empty:
                st.caption("freight 데이터 없음")
                filtered_f2 = ex_f
            else:
                dc_f2 = st.date_input(
                    "Freight 접수일 범위",
                    value=_offer_date_range_default(ex_f),
                    key="ex_both_f_dates",
                )
                if isinstance(dc_f2, tuple) and len(dc_f2) == 2:
                    dff_from, dff_to = dc_f2
                else:
                    dff_from = dff_to = dc_f2
                ff2 = {}
                for col, label in [
                    ("trader_name", "담당자"),
                    ("origin_port", "출발항"),
                    ("destination_port", "도착항"),
                    ("shipping_line", "선사"),
                ]:
                    if col in ex_f.columns:
                        of = _multiselect_options(ex_f, col)
                        if of:
                            ff2[col] = st.multiselect(label, of, key=f"ex_both_f_{col}")
                filtered_f2 = _apply_filters(
                    ex_f, "offer_date" if "offer_date" in ex_f.columns else None, dff_from, dff_to, ff2
                )
                st.caption(f"freight 행 수: **{len(filtered_f2)}**")

        st.divider()
        if filtered_m2.empty:
            st.caption("Market 미리보기: 없음")
        else:
            st.dataframe(filtered_m2.head(100), width="stretch", hide_index=True)
        if filtered_f2.empty:
            st.caption("Freight 미리보기: 없음")
        else:
            st.dataframe(filtered_f2.head(100), width="stretch", hide_index=True)

        xlsx_both = _to_excel_bytes({"market": filtered_m2, "freight": filtered_f2})
        st.download_button(
            "통합 Excel 다운로드 (market + freight 시트)",
            data=xlsx_both,
            file_name=f"trade_intel_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
