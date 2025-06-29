import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
from streamlit_folium import st_folium
import streamlit as st
import requests, math

# ────────────── 설정 ──────────────
st.set_page_config(layout="wide", page_title="청주시 경유지 최적 경로")
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1..."

# ────────────── 스타일 정의 ──────────────
CARD_STYLE = """
background: rgba(255,255,255,0.95);
border-radius: 12px;
box-shadow: 0 4px 12px rgba(0,0,0,0.1);
padding: 20px;
margin-bottom: 20px;
"""
BUTTON_CSS = """
<style>
button[kind="primary"] {background-color:#1f77b4; color:#fff;}
button[kind="secondary"] {background-color:#e74c3c; color:#fff;}
</style>
"""

# ────────────── 데이터 로드 ──────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 페이지 헤더 ──────────────
st.markdown("<h1 style='text-align:center; color:white;'>📍 청주시 경유지 최적 경로</h1>", unsafe_allow_html=True)
st.markdown("---")

# ────────────── 상단 메트릭 ──────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
mcol1, mcol2, _ = st.columns([1,1,4], gap="small")
mcol1.markdown(f"""
<div style="{CARD_STYLE}">
  <h4 style="margin:0;">⏱️ 예상 소요 시간</h4>
  <p style="font-size:24px; margin:4px 0 0;">{dur:.1f} 분</p>
</div>
""", unsafe_allow_html=True)
mcol2.markdown(f"""
<div style="{CARD_STYLE}">
  <h4 style="margin:0;">📏 예상 이동 거리</h4>
  <p style="font-size:24px; margin:4px 0 0;">{dist:.2f} km</p>
</div>
""", unsafe_allow_html=True)

# ────────────── 본문: 컨트롤 + 지도 ──────────────
ctrl_col, map_col = st.columns([1.5, 4], gap="large")

with ctrl_col:
    st.markdown(f"<div style='{CARD_STYLE}'>", unsafe_allow_html=True)
    st.subheader("🚗 경로 설정")
    mode  = st.radio("", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
    st.write("")  # spacer
    st.markdown(BUTTON_CSS, unsafe_allow_html=True)
    run   = st.button("✅ 경로 생성", key="run", type="primary")
    clear = st.button("🚫 초기화", key="clear", type="secondary")
    st.markdown("</div>", unsafe_allow_html=True)

with map_col:
    # (스냅 → Mapbox 호출 코드는 생략)
    # ...
    # folium.Map 생성 및 레이어 추가
    st.markdown(f"<div style='{CARD_STYLE} padding:8px;'>", unsafe_allow_html=True)
    m = folium.Map(location=[36.64,127.48], zoom_start=12)  # 임시 중심
    # ... 지도 요소 추가 ...
    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=650)
    st.markdown("</div>", unsafe_allow_html=True)

# ────────────── 사이드바: 순서 표시 ──────────────
with st.sidebar:
    st.markdown(f"<div style='{CARD_STYLE}'>", unsafe_allow_html=True)
    st.subheader("🔢 방문 순서")
    if "order" in st.session_state:
        for i,name in enumerate(st.session_state.order,1):
            st.write(f"**{i}.** {name}")
    else:
        st.write("경로를 생성해주세요")
    st.markdown("</div>", unsafe_allow_html=True)
