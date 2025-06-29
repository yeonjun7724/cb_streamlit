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

# ────────────── 0. Mapbox 토큰 ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ────────────── 1. 데이터 로드 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 2. Streamlit UI ──────────────
st.title("📍 청주시 경유지 최적 경로")
mode = st.radio("🚗 이동 모드 선택", ["driving", "walking"], horizontal=True)

start = st.selectbox("🏁 출발지 선택", gdf["name"].dropna().unique())
waypoints = st.multiselect("🧭 경유지 선택", [n for n in gdf["name"].dropna().unique() if n != start])

# 고정 UI: 버튼과 메트릭
col_btn, col_clear = st.columns(2)
with col_btn:
    find = st.button("✅ 최적 경로 찾기")
with col_clear:
    reset = st.button("🚫 초기화")

duration_placeholder = st.empty()
distance_placeholder = st.empty()

# ────────────── 3. 중심점 계산 ──────────────
center_lat = boundary.geometry.centroid.y.mean()
center_lon = boundary.geometry.centroid.x.mean()
if math.isnan(center_lat) or math.isnan(center_lon):
    center_lat, center_lon = 36.64, 127.48

# ────────────── 4. OSMnx 그래프 캐시 ──────────────
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

G = load_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 5. 좌표 스냅 ──────────────
selected = [start] + [wp for wp in waypoints if wp != start]
snapped = []
for name in selected:
    row = gdf[gdf["name"] == name].iloc[0]
    pt = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# 초기화 처리
if reset:
    for k in ["routing", "order", "duration", "distance"]:
        st.session_state.pop(k, None)

# ────────────── 6. API 호출 ──────────────
if find:
    if len(snapped) < 2:
        st.warning("출발지와 경유지를 최소 2개 선택해주세요.")
    else:
        coords = ";".join(f"{x},{y}" for x, y in snapped)
        if mode == "walking":
            url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords}"
            params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            key = "routes"
        else:
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords}"
            params = {
                "geometries":"geojson","overview":"full",
                "source":"first","destination":"last","roundtrip":"false",
                "access_token":MAPBOX_TOKEN
            }
            key = "trips"
        res = requests.get(url, params=params)
        data = res.json()
        if res.status_code != 200 or not data.get(key):
            st.error("경로를 생성할 수 없습니다. 토큰, 좌표, 모드를 확인하세요.")
        else:
            if mode == "walking":
                trip = data["routes"][0]
                route = trip["geometry"]["coordinates"]
                order = selected
            else:
                trip = data["trips"][0]
                route = trip["geometry"]["coordinates"]
                wps = data["waypoints"]
                visited = sorted(zip(wps, selected), key=lambda x: x[0]["waypoint_index"])
                order = [n for _, n in visited]
            dur = trip["duration"]/60
            dist = trip["distance"]/1000
            st.session_state.routing = route
            st.session_state.order = order
            st.session_state.duration = dur
            st.session_state.distance = dist

# ────────────── 7. 지도 그리기 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
folium.GeoJson(boundary, style_function=lambda f: {
    "fillColor":"#fff","color":"#444","weight":2,"fillOpacity":0.05
}).add_to(m)

# 모든 지점 클러스터 (기본 마커)
all_cluster = MarkerCluster().add_to(m)
for _, r in gdf.iterrows():
    folium.Marker([r.lat, r.lon], popup=r.name).add_to(all_cluster)

# 선택된 지점 강조 (파란 마커)
for idx, (x, y) in enumerate(snapped, start=1):
    folium.Marker(
        [y, x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {selected[idx-1]}"
    ).add_to(m)

# 라우팅 및 순서 숫자
if "routing" in st.session_state:
    rt = st.session_state.routing
    colors = ["red","orange","green","purple","brown","cadetblue"]
    # 각 segment polyline
    for i in range(len(rt)-1):
        segment = rt[i:i+2]
        folium.PolyLine(
            locations=[(p[1],p[0]) for p in segment],
            color=colors[i%len(colors)],
            weight=5,
            opacity=0.8
        ).add_to(m)
        # 숫자 표시
        mid = segment[1]
        folium.map.Marker(
            [mid[1], mid[0]],
            icon=DivIcon(html=f"<div style='font-size:14px;color:{colors[i%len(colors)]};'><b>{i+1}</b></div>")
        ).add_to(m)
    # 자동 줌
    lats = [p[1] for p in rt]; lons = [p[0] for p in rt]
    m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])

st_folium(m, width=800, height=600)

# ────────────── 8. 고정 메트릭 출력 ──────────────
if "duration" in st.session_state:
    duration_placeholder.metric("⏱️ 예상 소요 시간", f"{st.session_state.duration:.1f} 분")
    distance_placeholder.metric("📏 예상 이동 거리", f"{st.session_state.distance:.2f} km")
