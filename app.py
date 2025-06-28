# app.py

import os
import geopandas as gpd
import plotly.graph_objects as go
import requests
import streamlit as st

# ────────────── 1. 현재 경로 및 파일 존재 확인 ──────────────
st.write("✅ 현재 경로:", os.getcwd())
st.write("✅ cb_tour.shp 존재:", os.path.exists("cb_tour.shp"))

# ────────────── 2. Shapefile 읽기 (5179 → 4326) ──────────────
try:
    gdf = gpd.read_file("cb_tour.shp", engine="fiona")
    gdf = gdf.to_crs(epsg=4326)
    gdf["lon"] = gdf.geometry.x
    gdf["lat"] = gdf.geometry.y
    st.success("✅ Shapefile 읽기 성공")
except Exception as e:
    st.error(f"❌ Shapefile 읽기 오류: {e}")

# ────────────── 3. 선택된 좌표 리스트 초기화 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

# ────────────── 4. 포인트 선택 버튼 (고유 key 사용) ──────────────
st.write("## 📍 포인트 선택 시뮬레이션")

for idx, row in gdf.iterrows():
    label = f"선택: {row['lon']:.4f}, {row['lat']:.4f}"
    if st.button(label, key=f"select_btn_{idx}"):  # 👈 고유한 key 필수!
        st.session_state.selected_coords.append((row["lon"], row["lat"]))

# ────────────── 5. 선택된 좌표 리스트 출력 ──────────────
st.write("✅ 선택된 좌표:", st.session_state.selected_coords)

# ────────────── 6. 경로 초기화 버튼 ──────────────
if st.button("🚫 Clear Route"):
    st.session_state.selected_coords = []

# ────────────── 7. Plotly 지도 생성 ──────────────
fig = go.Figure()

# 전체 포인트 표시
fig.add_trace(go.Scattermapbox(
    lat=gdf["lat"],
    lon=gdf["lon"],
    mode='markers',
    marker=dict(size=10, color='red'),
    text=gdf.index.astype(str),
    name="All Points"
))

# 선택된 포인트 표시
if st.session_state.selected_coords:
    lon_list, lat_list = zip(*st.session_state.selected_coords)
    fig.add_trace(go.Scattermapbox(
        lat=lat_list,
        lon=lon_list,
        mode='markers',
        marker=dict(size=12, color='green'),
        name="Selected Points"
    ))

# ────────────── 8. Directions API 호출 및 경로 시각화 ──────────────
if len(st.session_state.selected_coords) >= 2:
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in st.session_state.selected_coords])
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
    params = {
        "geometries": "geojson",
        "overview": "full",
        "access_token": "YOUR_MAPBOX_TOKEN"  # ← 반드시 실제 토큰으로 교체!
    }

    st.write("📦 Directions API URL:", url)
    st.write("📦 Params:", params)

    response = requests.get(url, params=params)
    result = response.json()
    st.write("📦 API 응답:", result)

    if "routes" in result:
        route = result["routes"][0]["geometry"]["coordinates"]
        route_lon, route_lat = zip(*route)
        fig.add_trace(go.Scattermapbox(
            mode="lines",
            lon=route_lon,
            lat=route_lat,
            line=dict(width=3, color="blue"),
            name="Route"
        ))
    else:
        st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")

# ────────────── 9. 지도 Layout ──────────────
fig.update_layout(
    mapbox=dict(
        accesstoken="YOUR_MAPBOX_TOKEN",
        style="light",
        center=dict(lat=gdf["lat"].mean(), lon=gdf["lon"].mean()),
        zoom=10
    ),
    margin={"r":0,"t":0,"l":0,"b":0}
)

st.plotly_chart(fig, use_container_width=True)
