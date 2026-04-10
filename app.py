from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, timedelta

# 페이지 기본 설정
st.set_page_config(page_title="쌀 무역 인텔리전스", layout="wide")

# --- 구글 시트 연결 (최종 정리 버전) ---
try:
    # Secrets에서 값을 직접 읽어옴
    gs_info = st.secrets["connections"]["gsheets"]
    
    conn = st.connection(
        "gsheets", 
        type=GSheetsConnection, 
        spreadsheet=gs_info["spreadsheet"],
        service_account=gs_info["service_account"] # 명시적으로 전달
    )
except Exception as e:
    st.error(f"연결 설정 오류: {e}")
    st.stop()

def load_data(worksheet_name):
    try:
        # ttl="0"은 캐시를 쓰지 않고 실시간으로 구글 시트에서 가져오겠다는 뜻입니다.
        return conn.read(worksheet=worksheet_name, ttl="0")
    except Exception:
        # 데이터가 아예 없는 초기 상태라면 빈 데이터프레임을 반환합니다.
        return pd.DataFrame()

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

tab_dashboard, tab_market_entry, tab_freight_entry = st.tabs(["📊 대시보드", "🌾 쌀 오퍼 등록", "🚢 해상 운임 등록"])

# --- [1. 대시보드 탭] ---
with tab_dashboard:
    st.subheader("실시간 시장 데이터 분석")
    m_df = load_data("market")
    if not m_df.empty:
        st.dataframe(m_df.tail(15), width="stretch", hide_index=True)
    else:
        st.info("데이터가 없습니다.")

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
    
    # 수정사항 3: 원산지에 따른 항구 필터링을 위해 폼 밖에서 원산지 먼저 선택
    selected_origin_for_port = st.selectbox("원산지 선택 (항구 필터링용)", ORIGIN_OPTIONS, key="origin_port_filter")
    available_origin_ports = PORT_MAPPING.get(selected_origin_for_port, ["기타"])

    with st.form("freight_form"):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            f_offer_date = st.date_input("접수일", value=datetime.now())
            # 수정사항 3: 선택된 원산지에 맞는 출발항만 보여줌
            origin_port = st.selectbox("출발항 (Origin Port)", available_origin_ports)
        with f_col2:
            f_trader = st.selectbox("담당자", TRADER_OPTIONS, key="f_trader_sel")
            destination_port = st.selectbox("도착항 (Destination Port)", DESTINATION_PORT_OPTIONS)
        
        f_line = st.selectbox("선사", SHIPPING_OPTIONS)
        f_cost = st.number_input("운임 비용 (USD)", min_value=0.0, step=5.0)
        f_save = st.form_submit_button("운임 정보 저장")
        
        if f_save:
            f_df = load_data("freight")
            f_new = pd.DataFrame([{
                "offer_date": f_offer_date.isoformat(),
                "trader_name": f_trader,
                "origin_port": origin_port,
                "destination_port": destination_port,
                "shipping_line": f_line,
                "freight_cost": f_cost
            }])
            conn.update(worksheet="freight", data=pd.concat([f_df, f_new], ignore_index=True))
            st.success("운임 정보가 저장되었습니다.")
            st.rerun()