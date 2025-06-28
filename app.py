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

st.title("📍 청주시 경유지 최적 경로 (OSM 스냅 + 안전 체크 버전)")

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

# ────────────── 4. OSM 도로 Nearest Point 스냅 ──────────────
snapped_coords = []
if selected_names:
    points = []
    for name in selected_names:
        row = gdf[gdf["name"] == name].iloc[0]
        points.append(Point(row["lon"], row["lat"]))

    # ✔️ OSM 도로 가져오기 (네트워크: all, dist 넉넉히)
    center_lat = boundary.geometry.centroid.y.mean()
    center_lon = boundary.geometry.centroid.x.mean()

    # NaN 안전 디폴트
    if math.isnan(center_lat) or math.isnan(center_lon):
        center_lat = 36.64  # 청주시 위도 예시
        center_lon = 127.48 # 청주시 경도 예시

    G = ox.graph_from_point((center_lat, center_lon), dist=5000, network_type="all")
    edges = ox.graph_to_gdfs(G, nodes=False)

    for pt in points:
        edges["distance"] = edges.geometry.distance(pt)
        nearest_line = edges.loc[edges["distance"].idxmin()]
        nearest_point = nearest_line.geometry.interpolate(
            nearest_line.geometry.project(pt)
        )
        snapped_coords.append((nearest_point.x, nearest_point.y))

# ✔️ snapped_coords 안전 필터
if not snapped_coords:
    st.warning("⚠️ 스냅된 좌표가 없습니다. 출발지/경유지를 선택했는지 확인하세요.")

# Playground 디버그 출력
if snapped_coords:
    st.write("📌 스냅된 좌표 (lon, lat):", snapped_coords)
    st.info("👉 Playground: https://docs.mapbox.com/playground/optimization/ 에 붙여서 테스트!")

# ────────────── 5. 지도 ──────────────
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=12
)

# ✅ 청주시 행정경계만 GeoJSON으로 표시
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

# 스냅된 포인트만 마커로 표시
for idx, (lon, lat) in enumerate(snapped_coords, start=1):
    if idx == 1:
        icon_color = "green"
        icon_name = "play"
    else:
        icon_color = "blue"
        icon_name = "arrow-right"

    folium.Marker(
        location=[lat, lon],
        popup=f"{idx}. {selected_names[idx-1]}",
        tooltip=f"{idx}. {selected_names[idx-1]}",
        icon=folium.Icon(color=icon_color, icon=icon_name, prefix="glyphicon")
    ).add_to(m)

# 나머지 포인트
for _, row in gdf.iterrows():
    if row["name"] not in selected_names:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=row["name"],
            tooltip=row["name"],
            icon=folium.Icon(color="gray", icon="map-marker", prefix="glyphicon")
        ).add_to(marker_cluster)

# 경로 PolyLine + 화살표 + 순서배지
if "routing_result" in st.session_state and st.session_state["routing_result"]:
    route = st.session_state["routing_result"]
    ordered_names = st.session_state.get("ordered_names", selected_names)

    num_segments = len(ordered_names) - 1
    colors = ["blue", "green", "orange", "purple", "red", "pink"]

    points_per_leg = max(1, len(route) // max(1, num_segments))

    for i in range(num_segments):
        seg_points = route[i * points_per_leg : (i + 1) * points_per_leg + 1]

        folium.PolyLine(
            [(lat, lon) for lon, lat in seg_points],
            color=colors[i % len(colors)],
            weight=5
        ).add_to(m)

        for j in range(0, len(seg_points) - 1, max(1, len(seg_points) // 8)):
            lon1, lat1 = seg_points[j]
            lon2, lat2 = seg_points[j + 1]
            dx = lon2 - lon1
            dy = lat2 - lat1
            angle = math.degrees(math.atan2(dy, dx))

            folium.RegularPolygonMarker(
                location=[lat2, lon2],
                number_of_sides=3,
                radius=10,
                color=colors[i % len(colors)],
                fill_color=colors[i % len(colors)],
                rotation=angle
            ).add_to(m)

        mid_idx = len(seg_points) // 2
        lon_mid, lat_mid = seg_points[mid_idx]
        folium.map.Marker(
            [lat_mid, lon_mid],
            icon=folium.DivIcon(
                html=f"""<div style="font-size: 10pt; color: white; background: {colors[i % len(colors)]}; border-radius:50%; padding:4px">{i+1}</div>"""
            )
        ).add_to(m)

st_folium(m, height=600, width=800)

if "ordered_names" in st.session_state:
    st.write("🔢 최적 방문 순서:", st.session_state["ordered_names"])

# ────────────── 6. 버튼 고정 ──────────────
col1, col2 = st.columns([1, 1])

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

with col1:
    if st.button("✅ OSM Snap & 최적 경로 찾기"):
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
                st.error("❌ 최적화된 경로가 없습니다.\n📌 Playground에서 좌표를 직접 확인하세요!")
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
            st.warning("출발지와 경유지를 최소 1개 이상 선택하세요!")

with col2:
    if st.button("🚫 초기화"):
        for key in ["routing_result", "ordered_names", "start", "waypoints"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
