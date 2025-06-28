
import os
import geopandas as gpd
import plotly.graph_objects as go
import requests
import streamlit as st

# ────────────── 1. 파일 경로 및 존재 확인 ──────────────
st.write("✅ 현재 경로:", os.getcwd())
st.write("✅ cb_tour.shp 존재 여부:", os.path.exists("cb_tour.shp"))

# ────────────── 2. Shapefile 읽기 (5179 → 4326) ──────────────
try:
    gdf = gpd.read_file("cb_tour.shp", engine="fiona")  # ← pyogrio 대신 fiona 엔진 강제
    gdf = gdf.to_crs(epsg=4326)
    gdf["lon"] = gdf.geometry.x
    gdf["lat"] = gdf.geometry.y
except Exception as e:
    st.error(f"❌ Shapefile 읽기 오류: {e}")

# ────────────── 3. 선택 리스트 초기화 ──────────────
if "selected_coords" not in st.session_state:
    st.session_state.selected_coords = []

# ────────────── 4. 클릭 시뮬 (버튼으로 선택) ──────────────
st.write("## 포인트 선택 시뮬")
for idx, row in gdf.iterrows():
    if st.button(f"선택: {row['lon']:.4f}, {row['lat']:.4f}"):
        st.session_state.selected_coords.append((row["lon"], row["lat"]))

# ────────────── 5. 선택 결과 ──────────────
st.write("✅ 선택된 좌표:", st.session_state.selected_coords)

if st.button("🚫 Clear Route"):
    st.session_state.selected_coords = []

# ────────────── 6. Plotly 지도 ──────────────
fig = go.Figure()

# 전체 포인트
fig.add_trace(go.Scattermapbox(
    lat=gdf["lat"],
    lon=gdf["lon"],
    mode='markers',
    marker=dict(size=10, color='red'),
    text=gdf.index.astype(str),
))

# 선택된 포인트
if st.session_state.selected_coords:
    lon_list, lat_list = zip(*st.session_state.selected_coords)
    fig.add_trace(go.Scattermapbox(
        lat=lat_list,
        lon=lon_list,
        mode='markers',
        marker=dict(size=12, color='green'),
        name="Selected"
    ))

# ────────────── 7. Directions API 호출 ──────────────
if len(st.session_state.selected_coords) >= 2:
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in st.session_state.selected_coords])
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
    params = {
        "geometries": "geojson",
        "overview": "full",
        "access_token": "YOUR_MAPBOX_TOKEN"  # 반드시 실제 토큰으로 변경!
    }
    st.write("📦 API URL:", url)
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
        st.warning("❌ 경로 없음: " + result.get("message", "Unknown error"))

# ────────────── 8. 지도 Layout ──────────────
fig.update_layout(
    mapbox=dict(
        accesstoken="YOUR_MAPBOX_TOKEN",  # 동일 토큰으로!
        style="light",
        center=dict(lat=gdf["lat"].mean(), lon=gdf["lon"].mean()),
        zoom=10
    ),
    margin={"r":0,"t":0,"l":0,"b":0}
)

st.plotly_chart(fig, use_container_width=True)
