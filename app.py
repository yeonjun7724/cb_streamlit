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

# ────────────── 5. Nearest 스냅 (내부 계산용) ──────────────
snapped_coords = []
if selected_names:
    for name in selected_names:
        row = gdf[gdf["name"] == name].iloc[0]
        pt = Point(row["lon"], row["lat"])
        edges["distance"] = edges.geometry.distance(pt)
        nl = edges.loc[edges["distance"].idxmin()]
        sp = nl.geometry.interpolate(nl.geometry.project(pt))
        snapped_coords.append((sp.x, sp.y))

# ────────────── 6. Folium 지도 생성 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

# — 경계
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
    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="red", weight=4
    ).add_to(m)

# — 초기/선택/라우팅별 자동 줌
if "routing_result" in st.session_state:
    coords = st.session_state["routing_result"]
    lats = [lat for lon, lat in coords]
    lons = [lon for lon, lat in coords]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
elif snapped_coords:
    lats = [lat for lon, lat in snapped_coords]
    lons = [lon for lon, lat in snapped_coords]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
else:
    # 전체 지점 범위
    minx, miny, maxx, maxy = gdf.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]])

# — 레이어 토글
folium.LayerControl().add_to(m)

# — 지도 렌더링
st_folium(m, height=600, width=800)

# — 방문 순서 및 메트릭 표시
if "ordered_names" in st.session_state:
    st.write("🔢 최적 방문 순서:", st.session_state["ordered_names"])
    st.write(f"⏱️ 예상 소요 시간: {st.session_state['duration']:.1f} 분")
    st.write(f"📏 예상 이동 거리: {st.session_state['distance']:.2f} km")

# ────────────── 7. 버튼 로직 ──────────────
col1, col2 = st.columns(2)
with col1:
    if st.button("✅ 최적 경로 찾기"):
        if len(snapped_coords) < 2:
            st.warning("⚠️ 출발지와 경유지 2개 이상 선택해주세요!")
            st.stop()

        coords_str = ";".join(f"{lon},{lat}" for lon, lat in snapped_coords)

        if mode == "walking":
            url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords_str}"
            params = {
                "geometries": "geojson",
                "overview":   "full",
                "access_token": MAPBOX_TOKEN
            }
            key = "routes"
        else:
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords_str}"
            params = {
                "geometries":   "geojson",
                "overview":     "full",
                "source":       "first",
                "destination":  "last",
                "roundtrip":    "false",
                "access_token": MAPBOX_TOKEN
            }
            key = "trips"

        resp = requests.get(url, params=params)
        data = resp.json()
        if resp.status_code != 200 or not data.get(key):
            st.error("❌ 경로 생성 실패 – 좌표, 토큰, 모드를 확인해주세요.")
            st.stop()

        if mode == "walking":
            trip = data["routes"][0]
            route = trip["geometry"]["coordinates"]
            duration = trip.get("duration", 0) / 60
            distance = trip.get("distance", 0) / 1000
            ordered = selected_names
        else:
            trip = data["trips"][0]
            route = trip["geometry"]["coordinates"]
            duration = trip.get("duration", 0) / 60
            distance = trip.get("distance", 0) / 1000
            wps = data["waypoints"]
            visited = sorted(zip(wps, selected_names),
                             key=lambda x: x[0]["waypoint_index"])
            ordered = [n for _, n in visited]

        st.session_state["routing_result"] = route
        st.session_state["ordered_names"] = ordered
        st.session_state["duration"] = duration
        st.session_state["distance"] = distance

        st.success("✅ 최적 경로 생성됨!")
        st.rerun()

with col2:
    if st.button("🚫 초기화"):
        for k in ["routing_result", "ordered_names", "duration", "distance"]:
            st.session_state.pop(k, None)
        st.rerun()
