import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests

# ────────────── 1. 데이터 준비 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 Shapefile 포인트 멀티선택 → Mapbox 라우팅")

# ────────────── 2. 멀티셀렉트로 포인트 선택 ──────────────
# 포인트 ID 리스트
options = gdf.index.tolist()
selected_ids = st.multiselect("🔎 포인트 ID를 선택하세요", options)

# 선택된 좌표
selected_coords = [(gdf.loc[idx, "lon"], gdf.loc[idx, "lat"]) for idx in selected_ids]

# ────────────── 3. 지도 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 원본 포인트: 빨간 핀
for idx, row in gdf.iterrows():
    if idx in selected_ids:
        # 선택된 포인트는 초록색
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=f"ID: {idx}",
            tooltip=f"ID: {idx}",
            icon=folium.Icon(color="green", icon="ok-sign")
        ).add_to(m)
    else:
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=f"ID: {idx}",
            tooltip=f"ID: {idx}",
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(m)

# ────────────── 4. Directions API 결과 PolyLine 있으면 표시 ──────────────
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=4,
        opacity=0.8
    ).add_to(m)

st_folium(m, height=600, width=800)

st.write("✅ 선택된 포인트:", selected_coords)

# ────────────── 5. 선택 초기화 ──────────────
if st.button("🚫 선택 초기화"):
    if "routing_result" in st.session_state:
        del st.session_state["routing_result"]

# ────────────── 6. Directions API 호출 ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"  # 발급받은 pk.ey... 형식으로 교체

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
        st.write("📦 API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.session_state["routing_result"] = route
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")
            st.rerun()
        else:
            st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 포인트를 선택해야 경로가 만들어집니다.")
