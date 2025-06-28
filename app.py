import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests

# ────────────── 1. 데이터 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 name으로 포인트 선택 → Mapbox 라우팅 (화살표 포함)")

# ────────────── 2. 선택 메뉴 ──────────────
options = gdf["name"].tolist()

col1, col2, col3 = st.columns(3)

with col1:
    start = st.selectbox("🏁 출발지 선택", options, key="start")

with col2:
    waypoints = st.multiselect("🧭 경유지 선택 (순서대로)", options, key="waypoints")

with col3:
    end = st.selectbox("🏁 도착지 선택", options, key="end")

# 순서대로 리스트 만들기 (중복 방지)
selected_names = []
if start:
    selected_names.append(start)
for wp in waypoints:
    if wp != start and wp != end:
        selected_names.append(wp)
if end and end not in selected_names:
    selected_names.append(end)

# 선택된 name으로 좌표
selected_coords = []
for name in selected_names:
    row = gdf[gdf["name"] == name].iloc[0]
    selected_coords.append((row["lon"], row["lat"]))

st.write("✅ 선택 순서:", selected_names)

# ────────────── 3. 지도 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 모든 포인트
for _, row in gdf.iterrows():
    if row["name"] in selected_names:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=row["name"],
            tooltip=row["name"],
            icon=folium.Icon(color="green", icon="ok-sign", prefix="glyphicon")
        ).add_to(m)
    else:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=row["name"],
            tooltip=row["name"],
            icon=folium.Icon(color="red", icon="map-marker", prefix="glyphicon")
        ).add_to(m)

# PolyLine + 화살표 있으면
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]

    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=4,
        opacity=0.8
    ).add_to(m)

    # 화살표를 선 위에 추가 (예: 일부 점만 표시)
    for i in range(0, len(route) - 1, max(1, len(route) // 10)):
        lon1, lat1 = route[i]
        lon2, lat2 = route[i + 1]
        folium.RegularPolygonMarker(
            location=[lat2, lon2],
            number_of_sides=3,
            radius=8,
            color="blue",
            rotation=0
        ).add_to(m)

st_folium(m, height=600, width=800)

# ────────────── 4. 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    if "routing_result" in st.session_state:
        del st.session_state["routing_result"]

# ────────────── 5. Directions API ──────────────
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
        st.write("📦 Directions API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.session_state["routing_result"] = route
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")
            st.rerun()
        else:
            st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")
    else:
        st.warning("출발지와 도착지는 필수, 경유지는 선택!")
