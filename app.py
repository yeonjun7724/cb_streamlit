import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
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
st.title("📍 청주시 경유지 최적 경로 (안전 캐시 버전)")
mode = st.radio("🚗 이동 모드 선택:", ["driving", "walking"])

options = gdf["name"].dropna().unique().tolist()
col1, col2 = st.columns(2)
with col1:
    start = st.selectbox("🏁 출발지 선택", options)
with col2:
    waypoints = st.multiselect("🧭 경유지 선택", options)

selected_names = []
if start:
    selected_names.append(start)
for wp in waypoints:
    if wp != start:
        selected_names.append(wp)

# ────────────── 3. 중심점 계산 ──────────────
center_lat = boundary.geometry.centroid.y.mean()
center_lon = boundary.geometry.centroid.x.mean()
if math.isnan(center_lat) or math.isnan(center_lon):
    center_lat, center_lon = 36.64, 127.48

# ────────────── 4. OSMnx 그래프 캐시 ──────────────
@st.cache_data
def get_osm_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

G = get_osm_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 5. Nearest 스냅 (내부 계산만) ──────────────
snapped_coords = []
if selected_names:
    for name in selected_names:
        row = gdf[gdf["name"] == name].iloc[0]
        pt = Point(row["lon"], row["lat"])
        edges["distance"] = edges.geometry.distance(pt)
        nl = edges.loc[edges["distance"].idxmin()]
        sp = nl.geometry.interpolate(nl.geometry.project(pt))
        snapped_coords.append((sp.x, sp.y))
# >>> 스냅된 좌표 출력 부분 제거 <<<

# ────────────── 6. Folium 지도 생성 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
folium.GeoJson(
    boundary,
    name="청주시 경계",
    style_function=lambda x: {
        "fillColor":"#ffffff","color":"#000000","weight":1,"fillOpacity":0.1
    }
).add_to(m)

# — 모든 투어 지점 클러스터
all_cluster = MarkerCluster(name="All Tour Points").add_to(m)
for _, row in gdf.iterrows():
    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=row["name"],
        tooltip=row["name"],
        icon=folium.Icon(color="lightgray", prefix="glyphicon")
    ).add_to(all_cluster)

# — 기존 라우팅 경로
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    folium.PolyLine([(lat, lon) for lon, lat in route], color="red", weight=4).add_to(m)
    # 경로 범위로 자동 줌
    lats = [lat for lon, lat in route]
    lons = [lon for lon, lat in route]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

folium.LayerControl().add_to(m)
st_folium(m, height=600, width=800)

# — 방문 순서 출력
if "ordered_names" in st.session_state:
    st.write("🔢 최적 방문 순서:", st.session_state["ordered_names"])

# ────────────── 7. 버튼 로직 ──────────────
col1, col2 = st.columns(2)
with col1:
    if st.button("✅ 최적 경로 찾기"):
        if len(snapped_coords) < 2:
            st.warning("⚠️ 출발지/경유지 2개 이상 선택해주세요!")
            st.stop()

        coords_str = ";".join(f"{lon},{lat}" for lon, lat in snapped_coords)

        if mode == "walking":
            # 보행: Directions API
            url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords_str}"
            params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            key = "routes"
        else:
            # 운전: Optimized-Trips API
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords_str}"
            params = {
                "geometries":"geojson","overview":"full",
                "source":"first","destination":"last","roundtrip":"false",
                "access_token":MAPBOX_TOKEN
            }
            key = "trips"

        resp = requests.get(url, params=params)
        result = resp.json()
        if resp.status_code != 200 or not result.get(key):
            st.error("❌ 경로를 생성할 수 없습니다. 좌표나 토큰, 모드를 확인해주세요.")
            st.stop()

        # 경로·메트릭 추출
        if mode == "walking":
            trip = result["routes"][0]
            route = trip["geometry"]["coordinates"]
            duration = trip.get("duration",0)/60    # 분
            distance = trip.get("distance",0)/1000  # km
            st.session_state["ordered_names"] = selected_names
        else:
            trip = result["trips"][0]
            route = trip["geometry"]["coordinates"]
            duration = trip.get("duration",0)/60
            distance = trip.get("distance",0)/1000
            wps = result["waypoints"]
            visited = sorted(zip(wps, selected_names), key=lambda x:x[0]["waypoint_index"])
            st.session_state["ordered_names"] = [n for _,n in visited]

        st.session_state["routing_result"] = route

        # ← 여기가 추가된 부분: 소요시간/거리 모두 모드별로 표시
        st.write(f"⏱️ 예상 소요 시간: {duration:.1f}분")
        st.write(f"📏 예상 이동 거리: {distance:.2f}km")

        st.success("✅ 최적 경로 생성됨!")
        st.rerun()
with col2:
    if st.button("🚫 초기화"):
        for k in ["routing_result","ordered_names"]:
            st.session_state.pop(k,None)
        st.rerun()
