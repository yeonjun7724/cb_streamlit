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

boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

st.title("📍 청주시 경유지 최적 경로 (좌표 & 응답 디버깅 포함)")

# ────────────── 2. 선택 ──────────────
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

selected_coords = []
for name in selected_names:
    filtered = gdf[gdf["name"] == name]
    if filtered.empty:
        st.error(f"❌ 선택한 '{name}' 데이터가 없습니다.")
        st.stop()
    row = filtered.iloc[0]
    selected_coords.append((row["lon"], row["lat"]))

# 선택한 좌표 디버깅 출력
if selected_coords:
    st.write("🗺️ 선택된 좌표 (lon, lat):", selected_coords)

# ────────────── 3. 지도 ──────────────
m = folium.Map(
    location=[boundary.geometry.centroid.y.mean(), boundary.geometry.centroid.x.mean()],
    zoom_start=12
)

folium.GeoJson(
    boundary,
    name="청주시 행정경계",
    style_function=lambda x: {
        "fillColor": "#ffffff",
        "color": "#000000",
        "weight": 1,
        "fillOpacity": 0.1
    }
).add_to(m)

marker_cluster = MarkerCluster().add_to(m)

for idx, name in enumerate(selected_names, start=1):
    row = gdf[gdf["name"] == name].iloc[0]
    lat, lon = row["lat"], row["lon"]

    if idx == 1:
        icon_color = "green"
        icon_name = "play"
    else:
        icon_color = "blue"
        icon_name = "arrow-right"

    folium.Marker(
        location=[lat, lon],
        popup=f"{idx}. {name}",
        tooltip=f"{idx}. {name}",
        icon=folium.Icon(color=icon_color, icon=icon_name, prefix="glyphicon")
    ).add_to(m)

for _, row in gdf.iterrows():
    if row["name"] not in selected_names:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=row["name"],
            tooltip=row["name"],
            icon=folium.Icon(color="gray", icon="map-marker", prefix="glyphicon")
        ).add_to(marker_cluster)

# ────────────── 4. PolyLine + 화살표 ──────────────
if "routing_result" in st.session_state and st.session_state["routing_result"]:
    route = st.session_state["routing_result"]
    ordered_names = st.session_state.get("ordered_names", selected_names)

    num_segments = len(ordered_names) - 1
    colors = ["blue", "green", "orange", "purple", "red", "pink", "brown", "black"]

    points_per_leg = max(1, len(route) // max(1, num_segments))

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
                radius=12,
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

# 순서 리스트 출력
if "ordered_names" in st.session_state:
    st.write("🔢 최적 방문 순서:", st.session_state["ordered_names"])

# ────────────── 5. 버튼 고정 ──────────────
col1, col2 = st.columns([1, 1])

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

with col1:
    if st.button("✅ 최적 경로 찾기 (도착지 자동)"):
        if len(selected_coords) >= 2:
            coords_str = ";".join([f"{lon},{lat}" for lon, lat in selected_coords])
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/driving/{coords_str}"
            params = {
                "geometries": "geojson",
                "overview": "full",
                "source": "first",
                "roundtrip": "false",
                "access_token": MAPBOX_TOKEN
            }

            response = requests.get(url, params=params)
            result = response.json()

            st.write("📦 API 응답:", result)  # 디버깅 출력

            if not result or "trips" not in result or not result["trips"]:
                st.error("❌ 최적화된 경로가 없습니다.\n"
                         "👉 좌표가 도로 네트워크에 유효한지 확인하세요.\n"
                         "👉 너무 가까운 점은 안 됩니다.\n"
                         "👉 Playground로 직접 확인해보세요.")
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
            st.write("🔢 최적 방문 순서:", ordered_names)

            st.rerun()
        else:
            st.warning("⚠️ 출발지 + 경유지를 최소 1개 이상 선택하세요!")

with col2:
    if st.button("🚫 초기화"):
        for key in ["routing_result", "ordered_names", "start", "waypoints"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
