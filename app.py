# app.py

import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import osmnx as ox
import requests
from streamlit_folium import st_folium
from openai import OpenAI

# ───────────────────────────────
# 1) 기본 설정
# ───────────────────────────────
st.set_page_config(page_title="청주시 문화관광 대시보드", layout="wide")

MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN"  # 본인 토큰
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ───────────────────────────────
# 2) 데이터 로드
# ───────────────────────────────
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

# ───────────────────────────────
# 3) session_state 완전 초기화
# ───────────────────────────────
DEFAULT_STATE = {
    "route_order": [],
    "route_segments": [],
    "route_duration": 0.0,
    "route_distance": 0.0,
    "chat_messages": [
        {"role": "system", "content": "당신은 청주 문화유산을 소개하는 관광 가이드입니다."}
    ]
}

for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ───────────────────────────────
# 4) 좌우 레이아웃
# ───────────────────────────────
col_left, col_right = st.columns([1, 1])

# ───────────────────────────────
# 5) 좌측: 경유지 경로
# ───────────────────────────────
with col_left:
    st.header("🚗 청주시 경유지 최적 경로")

    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
    mode = st.radio("이동 모드", ["driving", "walking"], horizontal=True)

    create_clicked = st.button("✅ 경로 생성", key="create_route")
    clear_clicked = st.button("🚫 초기화", key="clear_route")

    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())

    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

    G = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    stops = [start] + wps
    snapped = []
    for nm in stops:
        r = gdf[gdf["name"] == nm].iloc[0]
        pt = Point(r.lon, r.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    if clear_clicked:
        for k in ["route_order", "route_segments", "route_duration", "route_distance"]:
            st.session_state[k] = DEFAULT_STATE[k]

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
            st.session_state["route_order"] = stops
            st.session_state["route_duration"] = td / 60
            st.session_state["route_distance"] = tl / 1000
            st.session_state["route_segments"] = segs

    dur = st.session_state.get("route_duration", 0.0)
    dist = st.session_state.get("route_distance", 0.0)
    st.write(f"⏱️ 예상 소요 시간: {dur:.1f}분 | 📏 이동 거리: {dist:.2f}km")

    m = folium.Map(location=[clat, clon], zoom_start=12)
    folium.GeoJson(boundary).add_to(m)
    mc = MarkerCluster().add_to(m)

    for _, row in gdf.iterrows():
        folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)

    order = st.session_state.get("route_order", stops)
    for idx, (x, y) in enumerate(snapped, 1):
        label = order[idx - 1] if idx - 1 < len(order) else ""
        folium.Marker([y, x],
                      tooltip=f"{idx}. {label}",
                      icon=folium.Icon(color="blue")).add_to(m)

    segments = st.session_state.get("route_segments", [])
    if segments:
        for seg in segments:
            folium.PolyLine([(pt[1], pt[0]) for pt in seg], color="red").add_to(m)

    st_folium(m, width="100%", height=600)

# ───────────────────────────────
# 6) 우측: GPT 관광지 챗봇
# ───────────────────────────────
with col_right:
    st.header("🏛️ 청주 문화관광 가이드")

    for msg in st.session_state["chat_messages"][1:]:
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
        user_input = st.text_input("📍 관광지명을 입력하세요")
        submitted = st.form_submit_button("보내기")

    if submitted and user_input:
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        with st.spinner("GPT 답변 생성 중..."):
            places = [p.strip() for p in user_input.split(',')]
            blocks = []
            for place in places:
                gpt_place = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "청주 관광 가이드"},
                        {"role": "user", "content": f"{place}의 역사, 계절, 포토스팟, 추천 코멘트를 알려줘."}
                    ]
                ).choices[0].message.content
                blocks.append(f"### {place}\n{gpt_place}")
            final_response = "\n\n".join(blocks)
            st.session_state["chat_messages"].append({"role": "assistant", "content": final_response})

# ───────────────────────────────
# 7) 디버깅 출력
# ───────────────────────────────
st.write("✅ session_state", dict(st.session_state))
