import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests, math
from streamlit_folium import st_folium

import pandas as pd
import re
from openai import OpenAI

# ──────────────────────────────────────────────
# 1) 페이지 & CSS
# ──────────────────────────────────────────────
st.set_page_config(page_title="청주시 경유지 & 관광 챗봇", layout="wide")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif; background: #F9F9F9; color: #333;
  }
  h1, h2, h4 { font-weight:700; }
  .card {
    background: linear-gradient(135deg, #FFFFFF 0%, #F6F8FA 100%);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    margin-bottom: 24px;
  }
  .stButton>button {
    border: none;
    border-radius: 8px;
    font-weight:600;
    padding: 12px 24px;
  }
  .btn-create {
    background: linear-gradient(90deg,#00C9A7,#008EAB); color:#FFF;
  }
  .btn-clear  {
    background:#E63946; color:#FFF;
  }
  .leaflet-container {
    border-radius:12px !important;
    box-shadow:0 2px 6px rgba(0,0,0,0.1);
  }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"  # 교체하세요
client = OpenAI(api_key=st.secrets["sk-proj-CrnyAxHpjHnHg6wu4iuTFlMRW8yFgSaAsmk8rTKcAJrYkPocgucoojPeVZ-uARjei6wyEILHmgT3BlbkFJ2_tSjk8mGQswRVBPzltFNh7zXYrsTfOIT3mzESkqrz2vbUsCIw3O1a2I6txAACdi673MitM1UA4"])

# ──────────────────────────────────────────────
# 2) 데이터 로드
# ──────────────────────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()

# ──────────────────────────────────────────────
# 3) 메인 타이틀
# ──────────────────────────────────────────────
st.title("📍 청주시 경유지 최적 경로 & 문화 관광 가이드 🏞️")

# ──────────────────────────────────────────────
# 4) 최적 경로 섹션
# ──────────────────────────────────────────────
st.subheader("🚗 경유지 최적 경로")

dur = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2)
m1.metric("예상 소요 시간 (분)", f"{dur:.1f}")
m2.metric("예상 이동 거리 (km)", f"{dist:.2f}")

col_ctrl, col_order, col_map = st.columns([1.5, 1, 4], gap="large")

with col_ctrl:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("경로 설정")
    mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
    create_clicked = st.button("✅ 경로 생성", key="run")
    clear_clicked  = st.button("🚫 초기화", key="clear")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
      <script>
        const btns = document.querySelectorAll('.stButton>button');
        if(btns[0]) btns[0].classList.add('btn-create');
        if(btns[1]) btns[1].classList.add('btn-clear');
      </script>
    """, unsafe_allow_html=True)

with col_order:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("방문 순서")
    if "order" in st.session_state:
        for i, name in enumerate(st.session_state.order, 1):
            st.markdown(f"{i}. {name}")
    else:
        st.info("경로 생성 후 순서가 표시됩니다.")
    st.markdown("</div>", unsafe_allow_html=True)

with col_map:
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

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
        for k in ["segments", "order", "duration", "distance"]:
            st.session_state.pop(k, None)

    if create_clicked and len(snapped) >= 2:
        segs, td, tl = [], 0.0, 0.0
        for i in range(len(snapped) - 1):
            x1, y1 = snapped[i]; x2, y2 = snapped[i + 1]
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
            r = requests.get(url, params=params); data=r.json() if r.status_code==200 else {}
            if data.get(key):
                leg = data[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]; tl += leg["distance"]
        if segs:
            st.session_state.order = stops
            st.session_state.duration = td / 60
            st.session_state.distance = tl / 1000
            st.session_state.segments = segs

    m = folium.Map(location=[clat, clon], tiles='CartoDB positron', zoom_start=12)
    folium.GeoJson(boundary).add_to(m)
    mc = MarkerCluster().add_to(m)
    for _, row in gdf.iterrows():
        folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)
    for idx, (x, y) in enumerate(snapped, 1):
        folium.Marker([y, x],
                      icon=folium.Icon(color="#008EAB", icon="flag"),
                      tooltip=f"{idx}. {st.session_state.get('order', stops)[idx - 1]}"
        ).add_to(m)
    if "segments" in st.session_state:
        palette = ["#FF6B6B", "#FFD93D", "#6BCB77"]
        for i, seg in enumerate(st.session_state.segments, 1):
            folium.PolyLine([(pt[1], pt[0]) for pt in seg],
                            color=palette[i % len(palette)], weight=5).add_to(m)
    st_folium(m, width="100%", height=600)

# ──────────────────────────────────────────────
# 5) 청주 문화 관광 가이드 챗봇
# ──────────────────────────────────────────────
st.markdown("---")
st.subheader("💬 청주 문화 관광 가이드 챗봇")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "당신은 청주 문화유산을 소개하는 공손한 챗봇입니다."}
    ]

# 이전 대화 출력
for msg in st.session_state.messages[1:]:
    if msg["role"] == "user":
        st.markdown(f"<div style='text-align:right;background:#dcf8c6;border-radius:10px;padding:8px;'>{msg['content']}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='background:#fff;border-radius:10px;padding:8px;'>{msg['content']}</div>", unsafe_allow_html=True)

with st.form("chat_form"):
    user_input = st.text_input("관광지 이름을 쉼표로 입력해주세요.")
    submitted = st.form_submit_button("보내기")

def format_cafes(cafes_df):
    cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
    result = []
    if len(cafes_df) == 0:
        return "☕ 주변에 등록된 카페 정보가 없어요."
    elif len(cafes_df) == 1:
        row = cafes_df.iloc[0]
        return f"- **{row['c_name']}** (⭐ {row['c_value']})"
    else:
        for _, row in cafes_df.iterrows():
            result.append(f"- **{row['c_name']}** (⭐ {row['c_value']})")
        return "\n".join(result)

if submitted and user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    places = [p.strip() for p in user_input.split(",")]
    blocks = []
    for place in places:
        matched = data[data["t_name"].str.contains(place, na=False)]
        gpt_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 청주 여행 가이드입니다."},
                {"role": "user", "content": f"{place}를 따뜻하게 소개해 주세요."}
            ]
        ).choices[0].message.content

        cafe_info = format_cafes(matched[["c_name", "c_value", "c_review"]]) if not matched.empty else "추천 카페 정보 없음"
        blocks.append(f"🏛️ {place}\n{gpt_response}\n\n{cafe_info}")

    final_response = "\n\n".join(blocks)
    st.session_state.messages.append({"role": "assistant", "content": final_response})
