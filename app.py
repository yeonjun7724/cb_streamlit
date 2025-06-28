import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests
from shapely.geometry import Point
from scipy.spatial import cKDTree

# ────────────── 1. 데이터 불러오기 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

# ────────────── 2. 선택 리스트 초기화 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

# ────────────── 3. Folium 지도 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 모든 포인트 마커 추가
for idx, row in gdf.iterrows():
    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=f"ID: {idx}"
    ).add_to(m)

# 이미 선택된 포인트는 다른 색으로
for lon, lat in st.session_state.selected_coords:
    folium.Marker(
        location=[lat, lon],
        icon=folium.Icon(color="green")
    ).add_to(m)

# ────────────── 4. 클릭 감지 ──────────────
output = st_folium(m, height=600, width=800)

if output["last_clicked"] is not None:
    lon = output["last_clicked"]["lng"]
    lat = output["last_clicked"]["lat"]

    # KDTree로 가장 가까운 포인트 찾기
    tree = cKDTree(gdf[["lon", "lat"]].values)
    dist, idx = tree.query([lon, lat])

    closest_point = (gdf.iloc[idx]["lon"], gdf.iloc[idx]["lat"])
    if closest_point not in st.session_state.selected_coords:
        st.session_state.selected_coords.append(closest_point)

st.write("✅ 선택된 포인트:", st.session_state.selected_coords)

# ────────────── 5. 선택 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    st.session_state.selected_coords = []

# ────────────── 6. [확인] 버튼 → Directions API ──────────────
if st.button("✅ 확인 (라우팅)"):
    if len(st.session_state.selected_coords) >= 2:
        coords_str = ";".join([f"{lon},{lat}" for lon, lat in st.session_state.selected_coords])
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "access_token": "YOUR_MAPBOX_TOKEN"  # ← 실제 토큰으로 교체!
        }
        st.write("📦 Directions URL:", url)
        response = requests.get(url, params=params)
        result = response.json()
        st.write("📦 API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")

            # 새 지도에 경로 시각화
            m2 = folium.Map(location=[st.session_state.selected_coords[0][1],
                                      st.session_state.selected_coords[0][0]],
                            zoom_start=12)

            for lon, lat in st.session_state.selected_coords:
                folium.Marker(location=[lat, lon]).add_to(m2)

            folium.PolyLine([(lat, lon) for lon, lat in route], color="blue", weight=4).add_to(m2)

            st_folium(m2, height=600, width=800)
        else:
            st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 포인트를 선택해야 경로 생성됩니다.")
