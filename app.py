import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import streamlit as st
import requests
import math

# ────────────── 1. 데이터 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 경유지 순서 + 구간별 색상 + 화살표 + 순서 배지 + 클러스터")

# ────────────── 2. 선택 ──────────────
options = gdf["name"].dropna().unique().tolist()

col1, col2, col3 = st.columns(3)

with col1:
    start = st.selectbox("🏁 출발지 선택", options, key="start")

with col2:
    waypoints = st.multiselect("🧭 경유지 선택 (순서대로)", options, key="waypoints")

with col3:
    end = st.selectbox("🏁 도착지 선택", options, key="end")

# 순서 리스트
selected_names = []
if start:
    selected_names.append(start)
for wp in waypoints:
    if wp != start and wp != end:
        selected_names.append(wp)
if end and end not in selected_names:
    selected_names.append(end)

# 안전한 포인트 추출
selected_coords = []
for name in selected_names:
    filtered = gdf[gdf["name"] == name]
    if filtered.empty:
        st.error(f"❌ 선택한 '{name}' 데이터가 없습니다.")
        st.stop()
    row = filtered.iloc[0]
    selected_coords.append((row["lon"], row["lat"]))

# ────────────── 3. 지도 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# MarkerCluster
marker_cluster = MarkerCluster().add_to(m)

# 선택된 포인트 마커
for idx, name in enumerate(selected_names, start=1):
    row = gdf[gdf["name"] == name].iloc[0]
    lat, lon = row["lat"], row["lon"]

    if idx == 1:
        icon_color = "green"
        icon_name = "play"
    elif idx == len(selected_names):
        icon_color = "red"
        icon_name = "stop"
    else:
        icon_color = "blue"
        icon_name = "arrow-right"

    folium.Marker(
        location=[lat, lon],
        popup=f"{idx}. {name}",
        tooltip=f"{idx}. {name}",
        icon=folium.Icon(color=icon_color, icon=icon_name, prefix="glyphicon")
    ).add_to(m)

# 나머지 포인트 클러스터
for _, row in gdf.iterrows():
    if row["name"] not in selected_names:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=row["name"],
            tooltip=row["name"],
            icon=folium.Icon(color="gray", icon="map-marker", prefix="glyphicon")
        ).add_to(marker_cluster)

# ────────────── 4. PolyLine + 화살표 + 순서 배지 ──────────────
if "routing_result" in st.session_state and st.session_state["routing_result"]:
    route = st.session_state["routing_result"]
    num_segments = len(selected_coords) - 1
    colors = ["blue", "green", "orange", "purple", "red"]

    points_per_leg = len(route) // num_segments
    for i in range(num_segments):
        seg_points = route[i * points_per_leg : (i + 1) * points_per_leg + 1]
        folium.PolyLine(
            [(lat, lon) for lon, lat in seg_points],
            color=colors[i % len(colors)],
            weight=5,
            opacity=0.8
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
                radius=8,
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

# 지도 출력
st_folium(m, height=600, width=800)

# ────────────── 5. 초기화 ──────────────
if st.button("🚫 초기화"):
    for key in ["routing_result", "start", "waypoints", "end"]:
        if key in st.session_state:
            del st.session_state[key]
    st.experimental_rerun()

# ────────────── 6. Directions API ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

if st.button("✅ 확인 (라우팅 실행)"):
    if len(selected_coords) >= 2:
        coords_str = ";".join([f"{lon},{lat}" for lon, lat in selected_coords])
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "access_token": MAPBOX_TOKEN
        }

        response = requests.get(url, params=params)
        result = response.json()

        if not result or "routes" not in result or not result["routes"]:
            st.error("❌ Directions API 응답에 routes가 없습니다.")
            st.stop()

        route = result["routes"][0]["geometry"]["coordinates"]
        st.session_state["routing_result"] = route
        st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")
        st.experimental_rerun()
    else:
        st.warning("출발지와 도착지는 필수, 경유지는 선택!")
