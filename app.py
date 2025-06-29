# app.py

import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests
import math
from streamlit_folium import st_folium
from openai import OpenAI

# ─────────────── 기본 설정 ───────────────
st.set_page_config(page_title="청주시 문화관광 대시보드", layout="wide")
MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN"  # ← 본인 Mapbox 토큰으로 교체
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ─────────────── 데이터 로드 ───────────────
@st.cache_data
def load_data():
    return pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()

@st.cache_data
def load_gis_data():
    gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
    gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
    boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
    return gdf, boundary

data = load_data()
gdf, boundary = load_gis_data()

# ─────────────── 안전한 session_state 초기화 ───────────────
if "route_order" not in st.session_state:
    st.session_state.route_order = []
if "route_segments" not in st.session_state:
    st.session_state.route_segments = []
if "route_duration" not in st.session_state:
    st.session_state.route_duration = 0.0
if "route_distance" not in st.session_state:
    st.session_state.route_distance = 0.0

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "system", "content": "당신은 청주 문화유산을 소개하는 관광 가이드입니다."}
    ]

# ─────────────── 컬럼 구성 ───────────────
col_left, col_right = st.columns([1, 1])

# ─────────────── 좌측: 경유지 최적 경로 ───────────────
with col_left:
    st.markdown("<h2>🚗 청주시 경유지 최적 경로</h2>", unsafe_allow_html=True)

    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
    mode  = st.radio("이동 모드", ["driving", "walking"], horizontal=True)

    create_clicked = st.button("✅ 경로 생성", key="route")
    clear_clicked  = st.button("🚫 초기화", key="clear")

    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())

    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

    G     = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    stops   = [start] + wps
    snapped = []
    for nm in stops:
        r = gdf[gdf["name"] == nm].iloc[0]
        pt = Point(r.lon, r.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    if clear_clicked:
        st.session_state.route_order = []
        st.session_state.route_segments = []
        st.session_state.route_duration = 0.0
        st.session_state.route_distance = 0.0

    if create_clicked and len(snapped) >= 2:
        segs, td, tl = [], 0.0, 0.0
        for i in range(len(snapped) - 1):
            x1, y1 = snapped[i]
            x2, y2 = snapped[i + 1]
            coord = f"{x1},{y1};{x2},{y2}"
            if mode == "walking":
                url, key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}", "routes"
                params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}
            else:
                url, key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}", "trips"
                params = {
                    "geometries": "geojson", "overview": "full",
                    "source": "first", "destination": "last", "roundtrip": "false",
                    "access_token": MAPBOX_TOKEN
                }
            r = requests.get(url, params=params)
            data = r.json() if r.status_code == 200 else {}
            if data.get(key):
                leg = data[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]
                tl += leg["distance"]
        if segs:
            st.session_state.route_order = stops
            st.session_state.route_duration = td / 60
            st.session_state.route_distance = tl / 1000
            st.session_state.route_segments = segs

    dur = st.session_state.get("route_duration", 0.0)
    dist = st.session_state.get("route_distance", 0.0)
    st.write(f"⏱️ 예상 소요 시간: {dur:.1f}분 | 📏 이동 거리: {dist:.2f}km")

    m = folium.Map(location=[clat, clon], zoom_start=12)
    folium.GeoJson(boundary).add_to(m)
    mc = MarkerCluster().add_to(m)
    for _, row in gdf.iterrows():
        folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)

    for idx, (x, y) in enumerate(snapped, 1):
        folium.Marker([y, x], icon=folium.Icon(color="blue"),
                      tooltip=f"{idx}. {st.session_state.get('route_order', stops)[idx - 1]}").add_to(m)

    if st.session_state.get("route_segments"):
        for seg in st.session_state.route_segments:
            folium.PolyLine([(pt[1], pt[0]) for pt in seg], color="red").add_to(m)
    st_folium(m, width="100%", height=600)

# ─────────────── 우측: 관광 챗봇 ───────────────
with col_right:
    st.markdown("<h2>🏛️ 청주 문화관광 가이드</h2>", unsafe_allow_html=True)

    for msg in st.session_state.chat_messages[1:]:
        if msg["role"] == "user":
            st.markdown(
                f"<div style='text-align:right;background:#dcf8c6;padding:8px;border-radius:10px'>{msg['content']}</div>",
                unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div style='text-align:left;background:#fff;padding:8px;border-radius:10px'>{msg['content']}</div>",
                unsafe_allow_html=True)

    st.divider()

    with st.form("chat_form"):
        user_input = st.text_input("📍 관광지명을 입력해보세요")
        submitted = st.form_submit_button("보내기")

    if submitted and user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.spinner("GPT 답변 생성 중..."):
            places = [p.strip() for p in user_input.split(',')]
            blocks = []
            for place in places:
                gpt_place = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "청주 관광 가이드"},
                        {"role": "user", "content": f"{place}의 역사와 포토스팟 알려줘"}
                    ]
                ).choices[0].message.content
                blocks.append(f"### {place}\n{gpt_place}")
            final_response = "\n\n".join(blocks)
            st.session_state.chat_messages.append({"role": "assistant", "content": final_response})
