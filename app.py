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
from html import escape

# ──────────────────────────────────────────────
# 페이지 설정 및 CSS
# ──────────────────────────────────────────────
st.set_page_config(page_title="청주시 통합 관광 시스템", layout="wide")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif; background: #F9F9F9; color: #333;
  }
  h1 { font-weight:700; }
  h4 { font-weight:600; }
  .card {
    background: linear-gradient(135deg, #FFFFFF 0%, #F6F8FA 100%);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    margin-bottom: 24px;
  }
  .card:hover {
    transform: translateY(-4px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.12);
  }
  .stButton>button {
    border: none;
    border-radius: 8px;
    font-weight:600;
    padding: 12px 24px;
    transition: all 0.2s ease-in-out;
  }
  .stButton>button:hover {
    opacity: 0.85;
    transform: translateY(-2px);
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
  .main .block-container {
    padding-top: 2rem; padding-bottom: 2rem; padding-left: 3rem; padding-right: 3rem;
  }
  .stTabs [data-baseweb="tab-list"] {
    gap: 24px;
  }
  .stTabs [data-baseweb="tab"] {
    height: 50px;
    background-color: white;
    border-radius: 8px;
    color: #333;
    font-weight: 600;
  }
  .stTabs [aria-selected="true"] {
    background-color: #00C9A7;
    color: white;
  }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 메인 헤더
# ──────────────────────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>🏛️ 청주시 통합 관광 시스템</h1>", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 탭 생성
# ──────────────────────────────────────────────
tab1, tab2 = st.tabs(["📍 경로 최적화", "🏞️ 문화 관광가이드"])

# ──────────────────────────────────────────────
# 탭 1: 경로 최적화
# ──────────────────────────────────────────────
with tab1:
    try:
        gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
        boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

        gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y

        MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN"

        dur = st.session_state.get("tour_duration", 0.0)
        dist = st.session_state.get("tour_distance", 0.0)
        m1, m2 = st.columns(2)

        with m1:
            st.markdown(f"<div class='card' style='text-align:center;'><h4>⏱️ 예상 소요 시간</h4><h2>{dur:.1f} 분</h2></div>", unsafe_allow_html=True)
        with m2:
            st.markdown(f"<div class='card' style='text-align:center;'><h4>📏 예상 이동 거리</h4><h2>{dist:.2f} km</h2></div>", unsafe_allow_html=True)

        col_ctrl, col_order, col_map = st.columns([1.5,1,4], gap="large")

        with col_ctrl:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("🚗 경로 설정")
            mode = st.radio("이동 모드", ["driving","walking"], horizontal=True)
            start = st.selectbox("출발지", gdf["name"].dropna().unique())
            wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
            st.markdown("</div>", unsafe_allow_html=True)

            create_clicked = st.button("✅ 경로 생성")
            clear_clicked = st.button("🚫 초기화")

        with col_order:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("🔢 방문 순서")
            if "tour_order" in st.session_state:
                for i, name in enumerate(st.session_state.tour_order, 1):
                    st.markdown(f"<p><strong>{i}.</strong> {name}</p>", unsafe_allow_html=True)
            else:
                st.write("경로 생성 후 순서가 표시됩니다.")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_map:
            ctr = boundary.geometry.centroid
            clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
            if pd.isna(clat) or pd.isna(clon):
                clat, clon = 36.64, 127.48

            @st.cache_data(allow_output_mutation=True)
            def load_graph(lat, lon):
                return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

            G = load_graph(clat, clon)
            edges = ox.graph_to_gdfs(G, nodes=False)

            stops = [start] + wps
            snapped = []
            for nm in stops:
                r = gdf[gdf["name"] == nm].iloc[0]
                if pd.isna(r.lon) or pd.isna(r.lat):
                    continue
                pt = Point(r.lon, r.lat)
                edges["d"] = edges.geometry.distance(pt)
                ln = edges.loc[edges["d"].idxmin()]
                sp = ln.geometry.interpolate(ln.geometry.project(pt))
                snapped.append((sp.x, sp.y))

            if clear_clicked:
                for k in ["tour_segments", "tour_order", "tour_duration", "tour_distance"]:
                    st.session_state.pop(k, None)

            if create_clicked and len(snapped) >= 2:
                segs, td, tl = [], 0.0, 0.0
                for i in range(len(snapped) - 1):
                    x1,y1 = snapped[i]; x2,y2 = snapped[i+1]
                    coord = f"{x1},{y1};{x2},{y2}"
                    if mode == "walking":
                        url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}"
                        key = "routes"
                        params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
                    else:
                        url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}"
                        key = "trips"
                        params = {"geometries":"geojson","overview":"full","source":"first",
                                  "destination":"last","roundtrip":"false","access_token":MAPBOX_TOKEN}
                    try:
                        r = requests.get(url, params=params)
                        data = r.json() if r.status_code == 200 else {}
                    except Exception as e:
                        st.warning(f"요청 오류: {e}")
                        data = {}

                    if data.get(key):
                        leg = data[key][0]
                        segs.append(leg["geometry"]["coordinates"])
                        td += leg["duration"]
                        tl += leg["distance"]
                if segs:
                    st.session_state.tour_order = stops
                    st.session_state.tour_duration = td/60
                    st.session_state.tour_distance = tl/1000
                    st.session_state.tour_segments = segs

            st.markdown("<div class='card'>", unsafe_allow_html=True)
            m = folium.Map(location=[clat, clon], tiles='CartoDB positron', zoom_start=12)

            folium.GeoJson(boundary).add_to(m)

            mc = MarkerCluster().add_to(m)
            for _, row in gdf.iterrows():
                folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)

            for idx, (x,y) in enumerate(snapped, 1):
                folium.Marker([y,x], icon=folium.Icon(color="blue", icon="flag"),
                              tooltip=f"{idx}. {st.session_state.get('tour_order', stops)[idx-1]}").add_to(m)

            if "tour_segments" in st.session_state:
                palette = ["#FF6B6B","#FFD93D","#6BCB77","#4D96FF","#E96479","#F9A826"]
                for i, seg in enumerate(reversed(st.session_state.tour_segments), 1):
                    folium.PolyLine([(pt[1],pt[0]) for pt in seg],
                                    color=palette[(i-1)%len(palette)], weight=6).add_to(m)
                    mid = seg[len(seg)//2]
                    safe_html = escape(str(i))
                    folium.map.Marker([mid[1], mid[0]],
                        icon=DivIcon(html=f"<div style='background:{palette[(i-1)%len(palette)]};"
                                          "color:#fff;border-radius:50%;width:28px;height:28px;"
                                          "line-height:28px;text-align:center;font-weight:600;'>"
                                          f"{safe_html}</div>")
                    ).add_to(m)

            st_folium(m, width="100%", height=650)
            st.markdown("</div>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"에러: {e}")

# ──────────────────────────────────────────────
# 탭 2: 문화 관광가이드 (요약)
# ──────────────────────────────────────────────
with tab2:
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ OpenAI API 키가 없습니다.")
        st.stop()
    client = OpenAI(api_key=api_key)

    try:
        data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()
    except:
        st.error("cj_data_final.csv 파일이 없습니다.")
        st.stop()

    # 이하 GPT 부분은 위 로직과 동일하게 적용하세요
    # => GPT 응답 처리 시 choices[] 길이 체크, 예외처리 포함

# ──────────────────────────────────────────────
# 사이드바 정보
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 사용 가이드\n\n경로 최적화, 문화관광 탭 이용방법 등")
