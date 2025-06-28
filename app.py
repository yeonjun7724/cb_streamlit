import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import osmnx as ox
from streamlit_folium import st_folium
import streamlit as st
import requests
import math

# ────────────── 1. 데이터 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

st.title("📍 청주시 경유지 최적 경로 (OSMnx 캐시 + 초경량 버전)")

# ────────────── 2. 모드 선택 ──────────────
mode = st.radio("🚗 이동 모드 선택:", ["driving", "walking"])

# ────────────── 3. 출발지 + 경유지 선택 ──────────────
options = gdf["name"].dropna().unique().tolist()

col1, col2 = st.columns(2)

with col1:
    start = st.selectbox("🏁 출발지 선택", options, key="start")

with col2:
    waypoints = st.multiselect("🧭 경유지 선택", options, key="waypoints")

selected_names = []
if start:
    selected_names.append(start)
for wp in waypoints:
    if wp != start:
        selected_names.append(wp)

# ────────────── 4. 안전 중심점 ──────────────
center_lat = boundary.geometry.centroid.y.mean()
center_lon = boundary.geometry.centroid.x.mean()

if math.isnan(center_lat) or math.isnan(center_lon):
    center_lat = 36.64
    center_lon = 127.48

# ────────────── 5. OSMnx 그래프 캐시 ──────────────
@st.cache_data
def get_osm_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

G = get_osm_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 6. Nearest Point 스냅 ──────────────
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

if not snapped_coords:
    st.warning("⚠️ 스냅된 좌표가 없습니다. 출발지/경유지를 선택하세요.")

if snapped_coords:
    st.write("📌 스냅된 좌표 (lon, lat):", snapped_coords)
    st.info("👉 Playground: https://docs.mapbox.com/playground/optimization/ 로 테스트!")

# ────────────── 7. 지도 ──────────────
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
    if idx == 1:
        icon_color = "green"
    else:
        icon_color = "blue"

    folium.Marker(
        location=[lat, lon],
        popup=f"{idx}. {selected_names[idx-1]}",
        tooltip=f"{idx}. {selected_names[idx-1]}",
        icon=folium.Icon(color=icon_color, prefix="glyphicon")
    ).add_to(m)

# ────────────── 경로 표시 (선 & 화살표 최소화) ──────────────
if "routing_result" in st.session_state and st.session_state["routing_result"]:
    route = st.session_state["routing_result"]
    ordered_names = st.session_state.get("ordered_names", selected_names)

    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=5
    ).add_to(m)

st_folium(m, height=600, width=800)

if "ordered_names" in st.session_state:
    st.write("🔢 최적 방문 순서:", st.session_state["ordered_names"])

# ────────────── 8. 버튼 ──────────────
col1, col2 = st.columns([1, 1])

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

with col1:
    if st.button("✅ 최적 경로 찾기"):
        if len(snapped_coords) >= 2:
            coords_str = ";".join([f"{lon},{lat}" for lon, lat in snapped_coords])
            profile = f"mapbox/{mode}"

            url = f"https://api.mapbox.com/optimized-trips/v1/{profile}/{coords_str}"
            params = {
                "geometries": "geojson",
                "overview": "full",
                "source": "first",
                "roundtrip": "false",
                "access_token": MAPBOX_TOKEN
            }
            response = requests.get(url, params=params)
            result = response.json()

            st.write("📦 Mapbox API 응답:", result)

            if not result or "trips" not in result or not result["trips"]:
                st.error("❌ 최적화된 경로가 없습니다.\n📌 Playground에서 좌표 확인하세요!")
                st.stop()

            route = result["trips"][0]["geometry"]["coordinates"]
            st.session_state["routing_result"] = route

            waypoints_result = result["waypoints"]
            visited_order = sorted(
                zip(waypoints_result, selected_names),
                key=lambda x: x[0]["waypoint_index"]
            )
            ordered_names = [name for _, name in visited_order]
            st.session_state["ordered_names"] = ordered_names

            st.success(f"✅ 최적화된 경로 생성! 점 수: {len(route)}")
            st.rerun()
        else:
            st.warning("⚠️ 출발지와 경유지를 최소 1개 이상 선택하세요!")

with col2:
    if st.button("🚫 초기화"):
        for key in ["routing_result", "ordered_names", "start", "waypoints"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
