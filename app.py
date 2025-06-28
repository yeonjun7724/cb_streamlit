import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests

# ────────────── 1. 데이터 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 드롭다운 + 멀티셀렉트로 경로 설정 → Mapbox 라우팅")

# ────────────── 2. 선택 메뉴 ──────────────
options = gdf.index.tolist()

col1, col2, col3 = st.columns(3)

with col1:
    start = st.selectbox("🏁 출발지 선택", options, key="start")

with col2:
    waypoints = st.multiselect("🧭 경유지 선택 (여러 개)", options, key="waypoints")

with col3:
    end = st.selectbox("🏁 도착지 선택", options, key="end")

# 중복 방지 + 순서 유지
selected_ids = []
if start is not None:
    selected_ids.append(start)
for wp in waypoints:
    if wp != start and wp != end:
        selected_ids.append(wp)
if end is not None and end not in selected_ids:
    selected_ids.append(end)

selected_coords = [(gdf.loc[idx, "lon"], gdf.loc[idx, "lat"]) for idx in selected_ids]

st.write("✅ 선택된 순서:", selected_ids)

# ────────────── 3. 지도 생성 ──────────────
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 모든 포인트: 빨간 핀 (기본)
for idx, row in gdf.iterrows():
    if idx in selected_ids:
        # 선택된 포인트: 초록 핀 + ok-sign
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=f"ID: {idx}",
            tooltip=f"ID: {idx}",
            icon=folium.Icon(color="green", icon="ok-sign", prefix="glyphicon")
        ).add_to(m)
    else:
        # 나머지: 빨간 핀 + map-marker
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=f"ID: {idx}",
            tooltip=f"ID: {idx}",
            icon=folium.Icon(color="red", icon="map-marker", prefix="glyphicon")
        ).add_to(m)

# 라우팅 결과 PolyLine 있으면 누적 표시
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="blue",
        weight=4,
        opacity=0.8
    ).add_to(m)

st_folium(m, height=600, width=800)

# ────────────── 4. 초기화 버튼 ──────────────
if st.button("🚫 선택 초기화"):
    if "routing_result" in st.session_state:
        del st.session_state["routing_result"]

# ────────────── 5. Directions API ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"  # 반드시 발급받은 토큰으로 교체하세요

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
        st.warning("출발지와 도착지를 반드시 선택하고, 경유지는 선택해도 되고 안해도 됩니다.")
