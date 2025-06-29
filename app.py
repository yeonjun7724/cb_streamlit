import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import osmnx as ox
from streamlit_folium import st_folium
import streamlit as st
import requests
import math

# ────────────── 0. 토큰 ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ────────────── 1. 데이터 로드 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 2. UI 설정 ──────────────
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

# ────────────── 5. Nearest 스냅 ──────────────
snapped_coords = []
if selected_names:
    for name in selected_names:
        row = gdf[gdf["name"] == name].iloc[0]
        pt = Point(row["lon"], row["lat"])
        edges["distance"] = edges.geometry.distance(pt)
        nearest_line = edges.loc[edges["distance"].idxmin()]
        nearest_point = nearest_line.geometry.interpolate(
            nearest_line.geometry.project(pt)
        )
        snapped_coords.append((nearest_point.x, nearest_point.y))

if snapped_coords:
    st.write("📌 스냅된 좌표:", snapped_coords)
    st.info("👉 https://docs.mapbox.com/playground/optimization/ 로 확인")

# ────────────── 6. Folium 지도 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
folium.GeoJson(
    boundary,
    name="청주시 경계",
    style_function=lambda x: {
        "fillColor": "#ffffff",
        "color": "#000000",
        "weight": 1,
        "fillOpacity": 0.1
    }
).add_to(m)

marker_cluster = MarkerCluster().add_to(m)
for idx, (lon, lat) in enumerate(snapped_coords, start=1):
    icon_color = "green" if idx == 1 else "blue"
    folium.Marker(
        location=[lat, lon],
        popup=f"{idx}. {selected_names[idx-1]}",
        tooltip=f"{idx}. {selected_names[idx-1]}",
        icon=folium.Icon(color=icon_color, prefix="glyphicon")
    ).add_to(marker_cluster)

if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    folium.PolyLine([(lat, lon) for lon, lat in route], color="blue", weight=5).add_to(m)

st_folium(m, height=600, width=800)

if "ordered_names" in st.session_state:
    st.write("🔢 최적 방문 순서:", st.session_state["ordered_names"])

# ────────────── 7. 버튼 로직 ──────────────
col1, col2 = st.columns(2)

with col1:
    if st.button("✅ 최적 경로 찾기"):
        # 최소 2점 이상 필요
        if len(snapped_coords) < 2:
            st.warning("⚠️ 출발지/경유지 2개 이상을 선택해주세요!")
            st.stop()

        # 1) coords_str
        coords_str = ";".join(f"{lon},{lat}" for lon, lat in snapped_coords)
        st.write("▶ coords_str:", coords_str)

        # 2) 요청 URL·파라미터
        profile = f"mapbox/{mode}"
        url = f"https://api.mapbox.com/optimized-trips/v1/{profile}/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "source": "first",
            "roundtrip": "false",  # 문자열로
            "access_token": MAPBOX_TOKEN
        }
        st.write("▶ 요청 URL:", url)
        st.write("▶ 요청 파라미터:", params)

        # 3) API 호출
        response = requests.get(url, params=params)
        st.write("▶ HTTP 상태 코드:", response.status_code)
        try:
            result = response.json()
        except ValueError:
            st.error("❌ JSON 디코딩 실패:\n" + response.text)
            st.stop()

        st.write("▶ Mapbox 응답:", result)

        # 4) trips 검사
        if response.status_code != 200 or not result.get("trips"):
            st.error("❌ 최적화 경로를 찾을 수 없습니다. Playground나 좌표를 다시 확인해주세요.")
            st.stop()

        # 5) 경로 & 순서 저장
        route = result["trips"][0]["geometry"]["coordinates"]
        st.session_state["routing_result"] = route

        waypoints = result["waypoints"]
        visited = sorted(
            zip(waypoints, selected_names),
            key=lambda x: x[0]["waypoint_index"]
        )
        st.session_state["ordered_names"] = [name for _, name in visited]

        st.success(f"✅ 최적 경로 생성됨! 포인트 수: {len(route)}")
        st.rerun()

with col2:
    if st.button("🚫 초기화"):
        for key in ["routing_result", "ordered_names"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
