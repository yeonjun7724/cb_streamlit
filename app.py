import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
from streamlit_folium import st_folium
import streamlit as st
import requests
import math

# ────────────── Page Config ──────────────
st.set_page_config(layout="wide", page_title="청주시 경유지 최적 경로")

# ────────────── Mapbox Token ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

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
m1, m2, _ = st.columns([1,1,4], gap="small")
m1.markdown(f"""
<div style="{CARD_STYLE}">
  <h4 style="margin:0;">⏱️ 예상 소요 시간</h4>
  <p style="font-size:24px; margin:4px 0 0;">{dur:.1f} 분</p>
</div>
""", unsafe_allow_html=True)
m2.markdown(f"""
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
    # 중심점 계산
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat):
        clat, clon = 36.64, 127.48

    # OSMnx 그래프 캐시
    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    G     = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    # 스톱 좌표 스냅
    stops   = [start] + wps
    snapped = []
    for name in stops:
        row = gdf[gdf["name"]==name].iloc[0]
        pt  = Point(row.lon, row.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    # 초기화 처리
    if clear:
        for k in ["segments","order","duration","distance"]:
            st.session_state.pop(k, None)

    # Mapbox API 호출 (각 구간)
    if run and len(snapped) >= 2:
        segments = []
        total_dur = 0.0
        total_dist= 0.0
        for i in range(len(snapped)-1):
            x1,y1 = snapped[i]
            x2,y2 = snapped[i+1]
            coord = f"{x1},{y1};{x2},{y2}"
            if mode=="walking":
                url, key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}", "routes"
                params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            else:
                url, key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}", "trips"
                params = {
                    "geometries":"geojson","overview":"full",
                    "source":"first","destination":"last","roundtrip":"false",
                    "access_token":MAPBOX_TOKEN
                }
            r = requests.get(url, params=params)
            j = r.json()
            if r.status_code == 200 and j.get(key):
                leg = j[key][0]
                segments.append(leg["geometry"]["coordinates"])
                total_dur  += leg["duration"]
                total_dist += leg["distance"]
            else:
                st.error("⚠️ 경로 생성 실패: 입력을 확인해주세요.")
                segments = []
                break
        if segments:
            st.session_state.order    = stops
            st.session_state.duration = total_dur / 60
            st.session_state.distance = total_dist / 1000
            st.session_state.segments = segments

    # 지도 컨테이너
    st.markdown(f"<div style='{CARD_STYLE} padding:8px;'>", unsafe_allow_html=True)
    m = folium.Map(location=[clat, clon], zoom_start=12)
    folium.GeoJson(
        boundary,
        style_function=lambda f: {
            "color":"#2A9D8F","weight":2,"dashArray":"5,5",
            "fillOpacity":0.1
        }
    ).add_to(m)

    # 모든 지점 (회색)
    mc = MarkerCluster().add_to(m)
    for _, r in gdf.iterrows():
        folium.Marker([r.lat, r.lon], popup=r.name,
                      icon=folium.Icon(color="gray")).add_to(mc)

    # 선택된 스톱 (파란색)
    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker(
            [y,x],
            icon=folium.Icon(color="blue", icon="info-sign"),
            tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)

    # 세그먼트 (뒤에서부터 그려 낮은 순서 위)
    if "segments" in st.session_state:
        colors = ["#e6194b","#3cb44b","#ffe119","#4363d8","#f58231","#911eb4"]
        for i in range(len(st.session_state.segments), 0, -1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine(
                locations=[(pt[1],pt[0]) for pt in seg],
                color=colors[(i-1)%len(colors)],
                weight=6, opacity=0.8
            ).add_to(m)
            mid = seg[len(seg)//2]
            html = f"""
            <div style="
                background:{colors[(i-1)%len(colors)]};
                color:white; border-radius:50%;
                width:28px;height:28px;line-height:28px;
                text-align:center;font-size:16px;
                font-weight:600;box-shadow:0 2px 6px rgba(0,0,0,0.3);
            ">{i}</div>
            """
            folium.map.Marker([mid[1],mid[0]], icon=DivIcon(html=html)).add_to(m)
        # 자동 줌
        pts = [pt for seg in st.session_state.segments for pt in seg]
        lats = [p[1] for p in pts]; lons = [p[0] for p in pts]
        m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
    else:
        sx,sy = snapped[0]
        m.location = [sy, sx]
        m.zoom_start = 15

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=650)
    st.markdown("</div>", unsafe_allow_html=True)
