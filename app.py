# app.py

import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import osmnx as ox
import requests
from streamlit_folium import st_folium
from openai import OpenAI
import math

# ──────────────────────────────
# ✅ 기본 설정 + CSS 테마
# ──────────────────────────────
st.set_page_config(page_title="청주시 경유지 & GPT", layout="wide")

st.markdown("""
<style>
body { background: #f9fafb; color: #333; font-family: 'Inter', sans-serif; }
h1,h2,h3,h4 { font-weight: 600; }
.card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }
.stButton>button { border-radius: 8px; font-weight: 600; padding: 10px 24px; }
.btn-create { background: linear-gradient(90deg, #00C9A7, #008EAB); color: #FFF; }
.btn-clear { background: #E63946; color: #FFF; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────
# ✅ API KEY
# ──────────────────────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)  # ✅ 직접 전달! 환경 변수 X

# ──────────────────────────────
# ✅ 데이터 로드
# ──────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ──────────────────────────────
# ✅ session_state 초기화
# ──────────────────────────────
DEFAULTS = {
    "order": [],
    "segments": [],
    "duration": 0.0,
    "distance": 0.0,
    "chat_messages": [{"role": "system", "content": "당신은 청주시 문화관광 전문 가이드입니다."}],
    "auto_gpt_input": ""
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────
# ✅ 헤더
# ──────────────────────────────
st.markdown("<h1 style='text-align:center;'>📍 청주시 경유지 & GPT</h1>", unsafe_allow_html=True)

col_left, col_right = st.columns([3, 1.5], gap="large")

# ──────────────── 좌측: 경유지 경로 ────────────────
with col_left:
    m1, m2 = st.columns(2, gap="small")
    with m1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("⏱️ **예상 소요 시간**")
        st.subheader(f"{st.session_state['duration']:.1f} 분")
        st.markdown("</div>", unsafe_allow_html=True)
    with m2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("📏 **예상 이동 거리**")
        st.subheader(f"{st.session_state['distance']:.2f} km")
        st.markdown("</div>", unsafe_allow_html=True)

    col_ctrl, col_order, col_map = st.columns([1.5, 1, 4], gap="large")

    with col_ctrl:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("🚗 경로 설정")
        mode = st.radio("이동 모드", ["driving","walking"], horizontal=True)
        start = st.selectbox("출발지", gdf["name"].dropna().unique())
        wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
        create_clicked = st.button("✅ 경로 생성", key="run")
        clear_clicked = st.button("🚫 초기화", key="clear")
        st.markdown("""
            <script>
              const btns = document.querySelectorAll('.stButton>button');
              if(btns[0]) btns[0].classList.add('btn-create');
              if(btns[1]) btns[1].classList.add('btn-clear');
            </script>
        """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_order:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("🔢 방문 순서")
        if st.session_state["order"]:
            for i, name in enumerate(st.session_state["order"], 1):
                st.markdown(f"{i}. {name}")
        else:
            st.markdown("🚫 경로 생성 후 표시됩니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_map:
        ctr = boundary.geometry.centroid
        clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
        if math.isnan(clat): clat, clon = 36.64, 127.48

        @st.cache_data
        def load_graph(lat, lon):
            return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
        G = load_graph(clat, clon)

        stops = [start] + wps
        snapped = []
        for nm in stops:
            row = gdf[gdf["name"] == nm].iloc[0]
            lon, lat = row.lon, row.lat
            node_id = ox.distance.nearest_nodes(G, lon, lat)
            node_data = G.nodes[node_id]
            snapped.append((node_data['x'], node_data['y']))

        if clear_clicked:
            for k in ["segments","order","duration","distance"]:
                st.session_state.pop(k, None)

        if create_clicked and len(snapped) >= 2:
            coords = ";".join([f"{x},{y}" for x, y in snapped])
            if len(snapped) > 2:
                url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords}"
                key = "trips"
                params = {
                    "geometries": "geojson", "overview": "full",
                    "source": "first", "destination": "last", "roundtrip": "false",
                    "access_token": MAPBOX_TOKEN
                }
            else:
                url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords}"
                key = "routes"
                params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}

            r = requests.get(url, params=params)
            data = r.json() if r.status_code == 200 else {}

            if key in data and data[key]:
                route = data[key][0]
                st.session_state["segments"] = [route["geometry"]["coordinates"]]
                st.session_state["duration"] = route["duration"] / 60
                st.session_state["distance"] = route["distance"] / 1000
                st.session_state["order"] = stops
            else:
                st.warning("❌ 경로 생성 실패!")

        m = folium.Map(location=[clat, clon], zoom_start=12)
        folium.GeoJson(boundary).add_to(m)
        mc = MarkerCluster().add_to(m)
        for _, row in gdf.iterrows():
            folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)

        for idx, ((x, y), name) in enumerate(zip(snapped, st.session_state.get("order", stops)), 1):
            folium.Marker([y, x], tooltip=f"{idx}. {name}",
                          icon=folium.Icon(color="#008EAB", icon="flag")).add_to(m)

        if st.session_state["segments"]:
            for seg in st.session_state["segments"]:
                folium.PolyLine([(pt[1], pt[0]) for pt in seg], color="red").add_to(m)

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st_folium(m, width="100%", height=600)
        st.markdown("</div>", unsafe_allow_html=True)

# ──────────────── 우측: GPT ────────────────
with col_right:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🏛️ 청주 GPT 가이드")

    for msg in st.session_state["chat_messages"][1:]:
        align = "right" if msg["role"] == "user" else "left"
        bg = "#dcf8c6" if msg["role"] == "user" else "#fff"
        st.markdown(
            f"<div style='text-align:{align};background:{bg};padding:8px;border-radius:10px;margin-bottom:6px'>{msg['content']}</div>",
            unsafe_allow_html=True)

    if st.button("🔁 방문 순서 가져오기"):
        route = st.session_state.get("order", [])
        if route:
            st.session_state["auto_gpt_input"] = ", ".join(route)
        else:
            st.warning("경로를 먼저 생성하세요!")

    with st.form("chat_form"):
        user_input = st.text_input(
            "📍 관광지명을 입력하세요",
            value=st.session_state.get("auto_gpt_input", ""),
            key="auto_gpt_input"
        )
        submitted = st.form_submit_button("보내기")

    if submitted and user_input:
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        with st.spinner("GPT 답변 생성 중..."):
            gpt_reply = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=st.session_state["chat_messages"]
            ).choices[0].message.content
            st.session_state["chat_messages"].append({"role": "assistant", "content": gpt_reply})

    st.markdown("</div>", unsafe_allow_html=True)
