# ────────────── 설치 필요 ──────────────
# pip install streamlit plotly geopandas requests

import geopandas as gpd
import plotly.graph_objects as go
import requests
import streamlit as st

# ────────────── 1. 데이터 불러오기 ──────────────
gdf = gpd.read_file("cb_tour.shp")
gdf = gdf.to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

# ────────────── 2. 선택 리스트 초기화 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

# ────────────── 3. 클릭 시뮬레이션 ──────────────
# 여기선 버튼으로 포인트 선택 시뮬
st.write("## 클릭할 포인트 선택")
for idx, row in gdf.iterrows():
    if st.button(f"선택: {row['lon']:.4f}, {row['lat']:.4f}"):
        st.session_state.selected_coords.append((row["lon"], row["lat"]))

# ────────────── 4. 선택된 포인트 확인 ──────────────
st.write("선택된 좌표:", st.session_state.selected_coords)

# ────────────── 5. Clear 버튼 ──────────────
if st.button("🚫 Clear Route"):
    st.session_state.selected_coords = []

# ────────────── 6. 지도 그리기 ──────────────
fig = go.Figure()

# 모든 포인트 마커
fig.add_trace(go.Scattermapbox(
    lat=gdf["lat"],
    lon=gdf["lon"],
    mode='markers',
    marker=dict(size=10, color='red'),
    text=gdf.index.astype(str),
))

# 선택된 포인트 마커
if st.session_state.selected_coords:
    lon_list, lat_list = zip(*st.session_state.selected_coords)
    fig.add_trace(go.Scattermapbox(
        lat=lat_list,
        lon=lon_list,
        mode='markers',
        marker=dict(size=12, color='green'),
        name="Selected"
    ))

# 선택된 좌표로 Directions API 호출
if len(st.session_state.selected_coords) >= 2:
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in st.session_state.selected_coords])
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
    params = {
        "geometries": "geojson",
        "access_token": "YOUR_MAPBOX_TOKEN"
    }
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
        st.warning("❌ 경로 없음: " + result.get("message", "Unknown error"))

# Layout 설정
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