import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests
from scipy.spatial import cKDTree

# ────────────── 1. 데이터 로딩 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

points_array = gdf[["lon", "lat"]].values
tree = cKDTree(points_array)

if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []
if "routing_result" not in st.session_state:
    st.session_state.routing_result = None

st.title("📍 Shapefile 포인트 선택 → Mapbox 라우팅 (디자인 개선)")

# ────────────── 2. 지도 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# ────────────── 3. 마커 렌더링 ──────────────
for idx, row in gdf.iterrows():
    point = (row["lon"], row["lat"])
    if point in st.session_state.selected_coords:
        # 선택된 포인트: 초록 핀 + ok-sign
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=f"ID: {idx}",
            tooltip="✅ 선택됨",
            icon=folium.Icon(color="green", icon="ok-sign", prefix="glyphicon")
        ).add_to(m)
    else:
        # 기본 포인트: 빨간 핀 + map-marker
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=f"ID: {idx}",
            tooltip=f"ID: {idx}",
            icon=folium.Icon(color="red", icon="map-marker", prefix="glyphicon")
        ).add_to(m)

# ────────────── 4. 경로 PolyLine 있으면 추가 ──────────────
if st.session_state.routing_result:
    folium.PolyLine(
        [(lat, lon) for lon, lat in st.session_state.routing_result],
        color="blue",
        weight=4,
        opacity=0.8
    ).add_to(m)

# ────────────── 5. 지도 띄우기 ──────────────
output = st_folium(m, height=600, width=800)

# ────────────── 6. 클릭 감지 + KDTree ──────────────
if output["last_clicked"] is not None:
    clicked_lon = output["last_clicked"]["lng"]
    clicked_lat = output["last_clicked"]["lat"]

    dist, idx = tree.query([clicked_lon, clicked_lat])

    if dist <= 0.001:
        closest = tuple(points_array[idx])
        if closest not in st.session_state.selected_coords:
            st.session_state.selected_coords.append(closest)
            st.success(f"✅ 선택된 포인트 추가: {closest}")
    else:
        st.warning("❌ 너무 멀리 클릭했습니다.")

st.write("👉 현재 선택된 포인트:", st.session_state.selected_coords)

# ────────────── 7. 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    st.session_state.selected_coords = []
    st.session_state.routing_result = None

# ────────────── 8. 라우팅 ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

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
        st.write("📦 Directions API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.session_state.routing_result = route
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")
            st.rerun()
        else:
            st.warning(f"❌ 경로 생성 실패: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 선택해야 경로 생성됩니다.")
