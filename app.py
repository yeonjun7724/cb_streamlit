import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests

# ────────────── 1. 데이터 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 드롭다운으로 포인트 순서 선택 → Mapbox 라우팅")

# ────────────── 2. 선택
options = gdf.index.tolist()

# 순차적으로 선택 예시
stop1 = st.selectbox("① 출발지 선택", options, key="stop1")
stop2 = st.selectbox("② 경유지 선택 (옵션)", options, key="stop2")
stop3 = st.selectbox("③ 도착지 선택", options, key="stop3")

# 중복 제거하고 순서 유지
selected_ids = []
for stop in [stop1, stop2, stop3]:
    if stop not in selected_ids:
        selected_ids.append(stop)

selected_coords = [(gdf.loc[idx, "lon"], gdf.loc[idx, "lat"]) for idx in selected_ids]
st.write("✅ 선택된 순서:", selected_coords)

# ────────────── 3. 지도 생성
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 모든 포인트: 빨간 CircleMarker
for idx, row in gdf.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"ID: {idx}"
    ).add_to(m)

# 선택된 포인트는 초록색
for lon, lat in selected_coords:
    folium.Marker(
        location=[lat, lon],
        icon=folium.Icon(color="green", icon="ok-sign", prefix="glyphicon")
    ).add_to(m)

# 라우팅 결과 PolyLine 있으면 그리기
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=4,
        opacity=0.8
    ).add_to(m)

st_folium(m, height=600, width=800)

# ────────────── 4. 초기화
if st.button("🚫 선택 초기화"):
    if "routing_result" in st.session_state:
        del st.session_state["routing_result"]

# ────────────── 5. Directions API
MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN"

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
        st.warning("출발지와 도착지를 반드시 선택해야 합니다.")
