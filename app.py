import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import osmnx as ox
import requests
from streamlit_folium import st_folium
from openai import OpenAI
import math

# ──────────────────────────────
# ✅ 직접 입력한 키
# ──────────────────────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"
gpt_api_key = "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"
client = OpenAI(api_key=gpt_api_key)

# ──────────────────────────────
# ✅ 데이터 로드
# ──────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()

# ──────────────────────────────
# ✅ 세션 기본값
# ──────────────────────────────
DEFAULTS = {
    "order": [],
    "segments": [],
    "duration": 0.0,
    "distance": 0.0,
    "messages": [{"role": "system", "content": "당신은 청주 문화관광 전문 가이드입니다."}],
    "auto_gpt_input": ""
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────
# ✅ 스타일
# ──────────────────────────────
st.set_page_config(page_title="청주시 경유지 & GPT 가이드", layout="wide")
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: #f9fafb;
    color: #333333;
  }
  .card {
    background: #ffffff;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    margin-bottom: 20px;
  }
  .kpi-value {
    font-size: 28px;
    font-weight: 600;
    margin: 8px 0;
  }
  .stButton>button {
    border-radius: 8px;
    font-weight: 600;
    padding: 12px 24px;
    width: 100%;
  }
  .btn-create { background: linear-gradient(90deg,#00C9A7,#008EAB); color: #ffffff; }
  .btn-clear { background: #E63946; color: #ffffff; }
  .leaflet-container {
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  }
</style>
""", unsafe_allow_html=True)
st.markdown("""
<script>
  const btns = window.parent.document.querySelectorAll('.stButton>button');
  if (btns[0]) btns[0].classList.add('btn-create');
  if (btns[1]) btns[1].classList.add('btn-clear');
</script>
""", unsafe_allow_html=True)

# ──────────────────────────────
# ✅ 상단 타이틀
# ──────────────────────────────
st.markdown("<h1 style='text-align:center;'>📍 청주시 경로 & GPT 대시보드</h1>", unsafe_allow_html=True)

# ------------------------------
# ✅ KPI 카드 + 버튼
# ------------------------------
col1, col2 = st.columns(2)
with col1:
    kpi1, kpi2 = st.columns(2)
    with kpi1:
        st.markdown("<div class='card'>예상 소요 시간</div>", unsafe_allow_html=True)
        st.subheader(f"{st.session_state['duration']:.1f} 분")
    with kpi2:
        st.markdown("<div class='card'>예상 이동 거리</div>", unsafe_allow_html=True)
        st.subheader(f"{st.session_state['distance']:.2f} km")

btn_col1, btn_col2 = st.columns(2, gap="small")
with btn_col1:
    create_clicked = st.button("✅ 경로 생성")
with btn_col2:
    clear_clicked = st.button("🚫 초기화")

# ------------------------------
# ✅ 경로 설정 + 방문순서 + 지도
# ------------------------------
col_ctrl, col_order, col_map = st.columns([1.5, 1, 4], gap="large")

with col_ctrl:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🚗 경로 설정")
    mode = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
    st.markdown("</div>", unsafe_allow_html=True)

with col_order:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🔢 방문 순서")
    if st.session_state["o]()_
