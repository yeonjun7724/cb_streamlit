import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests
from scipy.spatial import cKDTree

# ────────────── 1. Shapefile 불러오기 ──────────────
# EPSG:5179 → EPSG:4326 좌표계 변환
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

# KDTree 준비
points_array = gdf[["lon", "lat"]].values
tree = cKDTree(points_array)

# ────────────── 2. 선택 리스트 초기화 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

st.title("📍 Shapefile 포인트 선택 → Mapbox 라우팅")

# ────────────── 3. 지도 생성 ──────────────
m = folium.Map(
    location=[gdf["lat"].mean(), gdf["lon"].mean()],
    zoom_start=12
)

# 원본 포인트 전부 마커로 표시
for idx, row in gdf.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"ID: {idx}"
    ).add_to(m)

# 이미 선택된 포인트는 초록색으로 표시
for lon, lat in st.session_state.selected_coords:
    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color="green",
        fill=True,
        fill_opacity=1.0
    ).add_to(m)

# ────────────── 4. 지도 띄우고 클릭 감지 ──────────────
output = st_folium(m, height=600, width=800)

if output["last_clicked"] is not None:
    clicked_lon = output["last_clicked"]["lng"]
    clicked_lat = output["last_clicked"]["lat"]

    dist, idx = tree.query([clicked_lon, clicked_lat])

    if dist <= 0.001:  # 반경 약 100m 제한
        closest_point = tuple(points_array[idx])
        if closest_point not in st.session_state.selected_coords:
            st.session_state.selected_coords.append(closest_point)
            st.success(f"✅ 선택된 포인트 추가: {closest_point}")
    else:
        st.warning("❌ 너무 멀리 클릭했습니다. 포인트 근처를 클릭하세요!")

st.write("👉 현재 선택된 포인트:", st.session_state.selected_coords)

# ────────────── 5. 선택 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    st.session_state.selected_coords = []

# ────────────── 6. Mapbox Directions API 호출 ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"  # ← 실제 발급받은 토큰으로 교체하세요!

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

        st.write("📦 Directions URL:", url)
        response = requests.get(url, params=params)
        result = response.json()
        st.write("📦 API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")

            # ────────────── 7. 새 지도에 선택 포인트 + 경로 표시 ──────────────
            m2 = folium.Map(
                location=[coords[0][1], coords[0][0]],
                zoom_start=12
            )

            # 선택된 포인트 마커
            for lon, lat in coords:
                folium.Marker(
                    location=[lat, lon],
                    icon=folium.Icon(color="green")
                ).add_to(m2)

            # 경로 PolyLine 추가
            folium.PolyLine(
                [(lat, lon) for lon, lat in route],
                color="blue",
                weight=4,
                opacity=0.7
            ).add_to(m2)

            st_folium(m2, height=600, width=800)

        else:
            st.warning(f"❌ 경로 생성 실패: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 포인트를 선택해야 경로를 생성할 수 있습니다.")
