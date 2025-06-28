import streamlit as st
from streamlit_folium import st_folium
import folium
import geopandas as gpd
import requests

# Shapefile 읽기 (좌표계 변환)
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)

# 선택 리스트 초기화
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

# Folium 지도 생성
m = folium.Map(location=[gdf.geometry.y.mean(), gdf.geometry.x.mean()], zoom_start=10)

# 모든 포인트 마커
for idx, row in gdf.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"ID: {idx}"
    ).add_to(m)

# 클릭 이벤트 캡처
output = st_folium(m, height=600, width=800)

# 클릭된 좌표 처리
if output["last_clicked"] is not None:
    lon, lat = output["last_clicked"]["lng"], output["last_clicked"]["lat"]
    if (lon, lat) not in st.session_state.selected_coords:
        st.session_state.selected_coords.append((lon, lat))

st.write("✅ 선택된 좌표:", st.session_state.selected_coords)

# 선택 초기화
if st.button("🚫 Clear"):
    st.session_state.selected_coords = []

# Directions API 호출
if len(st.session_state.selected_coords) >= 2:
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in st.session_state.selected_coords])
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
        st.write("✅ 경로 좌표 수:", len(route))
    else:
        st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")
