import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests
from scipy.spatial import cKDTree
import numpy as np

# ────────────── Shapefile 불러오기 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

points_array = gdf[["lon", "lat"]].values
tree = cKDTree(points_array)

# ────────────── 선택 리스트 초기화 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

# ────────────── Folium 지도 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 원본 포인트 마커
for idx, row in gdf.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"ID: {idx}"
    ).add_to(m)

# 이미 선택된 포인트 마커
for lon, lat in st.session_state.selected_coords:
    folium.CircleMarker(
        location=[lat, lon],
        radius=6,
        color="green",
        fill=True,
        fill_opacity=1.0
    ).add_to(m)

# ────────────── 지도 띄우고 클릭 감지 ──────────────
output = st_folium(m, height=600, width=800)

if output["last_clicked"] is not None:
    clicked_lon = output["last_clicked"]["lng"]
    clicked_lat = output["last_clicked"]["lat"]
    dist, idx = tree.query([clicked_lon, clicked_lat])

    # 대략 0.001 deg ≈ 100m 정도, 원하는 반경으로 제한
    if dist <= 0.001:  
        closest = tuple(points_array[idx])
        if closest not in st.session_state.selected_coords:
            st.session_state.selected_coords.append(closest)
            st.success(f"✅ 선택된 포인트 추가: {closest}")
    else:
        st.warning("❌ 너무 멀리 클릭했습니다. 포인트 가까이 클릭하세요.")

st.write("👉 현재 선택된 포인트:", st.session_state.selected_coords)

# ────────────── 선택 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    st.session_state.selected_coords = []

# ────────────── Directions API ──────────────
if st.button("✅ 확인 (라우팅)"):
    coords = st.session_state.selected_coords
    if len(coords) >= 2:
        coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords])
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "access_token": "YOUR_MAPBOX_TOKEN"
        }
        response = requests.get(url, params=params)
        result = response.json()
        st.write("📦 API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]

            # 새로운 지도에 경로 그리기
            m2 = folium.Map(location=[coords[0][1], coords[0][0]], zoom_start=12)

            # 선택된 포인트 마커
            for lon, lat in coords:
                folium.Marker(location=[lat, lon]).add_to(m2)

            folium.PolyLine([(lat, lon) for lon, lat in route], color="blue", weight=4).add_to(m2)
            st_folium(m2, height=600, width=800)
        else:
            st.warning(f"❌ 경로 생성 실패: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 포인트를 선택해야 합니다.")
