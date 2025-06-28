import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests
import math

# ────────────── 1. 데이터 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 경유지 순서 + 화살표 + 순서 Marker")

# ────────────── 2. 선택 ──────────────
options = gdf["name"].tolist()

col1, col2, col3 = st.columns(3)

with col1:
    start = st.selectbox("🏁 출발지", options, key="start")

with col2:
    waypoints = st.multiselect("🧭 경유지 (순서대로)", options, key="waypoints")

with col3:
    end = st.selectbox("🏁 도착지", options, key="end")

# 선택 순서
selected_names = []
if start: selected_names.append(start)
for wp in waypoints:
    if wp != start and wp != end:
        selected_names.append(wp)
if end and end not in selected_names:
    selected_names.append(end)

# 좌표 리스트
selected_coords = []
for name in selected_names:
    row = gdf[gdf["name"] == name].iloc[0]
    selected_coords.append((row["lon"], row["lat"]))

st.write("✅ 선택 순서:", selected_names)

# ────────────── 3. 지도 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 포인트: 순서에 따라 아이콘 다르게
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

# 나머지 포인트
for _, row in gdf.iterrows():
    if row["name"] not in selected_names:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=row["name"],
            tooltip=row["name"],
            icon=folium.Icon(color="gray", icon="map-marker", prefix="glyphicon")
        ).add_to(m)

# PolyLine 있으면 추가 + 화살표
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]

    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=5,
        opacity=0.8
    ).add_to(m)

    # 화살표: 일정 간격마다
    for i in range(0, len(route) - 1, max(1, len(route) // 10)):
        lon1, lat1 = route[i]
        lon2, lat2 = route[i + 1]

        dx = lon2 - lon1
        dy = lat2 - lat1
        angle = math.degrees(math.atan2(dy, dx))

        folium.RegularPolygonMarker(
            location=[lat2, lon2],
            number_of_sides=3,
            radius=8,
            color="blue",
            fill_color="blue",
            rotation=angle
        ).add_to(m)

st_folium(m, height=600, width=800)

# ────────────── 4. 초기화 ──────────────
if st.button("🚫 초기화"):
    if "routing_result" in st.session_state:
        del st.session_state["routing_result"]

# ────────────── 5. Directions API ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

if st.button("✅ 확인 (라우팅)"):
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
        st.write("📦 Directions API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.session_state["routing_result"] = route
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")
            st.rerun()
        else:
            st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")
    else:
        st.warning("출발지와 도착지를 선택하세요. 경유지는 선택해도 되고 안 해도 됩니다.")
