import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests
from scipy.spatial import cKDTree

# ────────────── 1. 데이터 준비 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

points_array = gdf[["lon", "lat"]].values
tree = cKDTree(points_array)

# ────────────── 2. 상태 관리 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

st.title("📍 Shapefile 포인트 선택 → Mapbox 라우팅")

# ────────────── 3. 지도 객체 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 모든 포인트 마커
for idx, row in gdf.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"ID: {idx}"
    ).add_to(m)

# 선택된 포인트 마커
for lon, lat in st.session_state.selected_coords:
    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color="green",
        fill=True,
        fill_opacity=1.0
    ).add_to(m)

# ────────────── 4. 확인 버튼 눌러서 라우팅 했는지 체크 ──────────────
# → 라우팅 결과 있으면 PolyLine 그려서 같은 지도에 추가
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=4,
        opacity=0.7
    ).add_to(m)

# ────────────── 5. 지도 띄우고 클릭 감지 ──────────────
output = st_folium(m, height=600, width=800)

if output["last_clicked"] is not None:
    clicked_lon = output["last_clicked"]["lng"]
    clicked_lat = output["last_clicked"]["lat"]

    dist, idx = tree.query([clicked_lon, clicked_lat])

    if dist <= 0.001:  # 약 100m
        closest_point = tuple(points_array[idx])
        if closest_point not in st.session_state.selected_coords:
            st.session_state.selected_coords.append(closest_point)
            st.success(f"✅ 선택된 포인트 추가: {closest_point}")
    else:
        st.warning("❌ 너무 멀리 클릭했습니다.")

st.write("👉 현재 선택된 포인트:", st.session_state.selected_coords)

# ────────────── 6. 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    st.session_state.selected_coords = []
    if "routing_result" in st.session_state:
        del st.session_state["routing_result"]

# ────────────── 7. [확인] 버튼 → Directions API ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"  # ← 실제 발급 토큰으로 교체

if st.button("✅ 확인 (라우팅 실행)"):
    coords = st.session_state.selected_coords
    if len(coords) >= 2:
        coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords])
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "access_token": MAPBOX_TOKEN
        }

        response = requests.get(url, params=params)
        result = response.json()

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.session_state["routing_result"] = route
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")
            st.rerun()  # 📌 다시 실행해서 PolyLine까지 반영된 새 지도 출력
        else:
            st.warning(f"❌ 경로 실패: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 선택해야 합니다.")
