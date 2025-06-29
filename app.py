import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
from streamlit_folium import st_folium
import streamlit as st
import requests
import math

# ────────────── 0. Mapbox 토큰 ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

st.set_page_config(layout="wide")
st.title("📍 청주시 경유지 최적 경로")

# ────────────── 사이드바: 고정 방문 순서 ──────────────
with st.sidebar:
    st.header("🔢 최적 방문 순서")
    if "order" in st.session_state:
        for i, nm in enumerate(st.session_state.order, 1):
            st.write(f"{i}. {nm}")
    else:
        st.write("경로를 생성하세요.")

# ────────────── 1. 데이터 로드 ──────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 2. UI: 모드·출발·경유 ──────────────
mode   = st.radio("🚗 이동 모드 선택", ["driving", "walking"], horizontal=True)
start  = st.selectbox("🏁 출발지 선택", gdf["name"].dropna().unique())
wps    = st.multiselect("🧭 경유지 선택",
                        [n for n in gdf["name"].dropna().unique() if n != start])

col1, col2 = st.columns(2)
with col1:
    run = st.button("✅ 최적 경로 찾기")
with col2:
    clear = st.button("🚫 초기화")

# ────────────── 3. 고정 메트릭 ──────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2)
m1.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
m2.metric("📏 예상 이동 거리", f"{dist:.2f} km")

# ────────────── 4. 중심점 계산 ──────────────
ctr = boundary.geometry.centroid
clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
if math.isnan(clat):
    clat, clon = 36.64, 127.48

# ────────────── 5. OSMnx 캐시 ──────────────
@st.cache_data
def get_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
G     = get_graph(clat, clon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 6. 좌표 스냅 ──────────────
stops   = [start] + wps
snapped = []
for name in stops:
    row = gdf[gdf["name"] == name].iloc[0]
    pt  = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# 초기화
if clear:
    for k in ["routing", "order", "duration", "distance"]:
        st.session_state.pop(k, None)

# ────────────── 7. Mapbox API 호출 ──────────────
if run and len(snapped) >= 2:
    coord_str = ";".join(f"{x},{y}" for x, y in snapped)
    if mode == "walking":
        url    = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord_str}"
        params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
        key    = "routes"
    else:
        url    = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord_str}"
        params = {
            "geometries":"geojson","overview":"full",
            "source":"first","destination":"last","roundtrip":"false",
            "access_token":MAPBOX_TOKEN
        }
        key    = "trips"
    res = requests.get(url, params=params)
    j   = res.json()
    if res.status_code == 200 and j.get(key):
        if mode == "walking":
            trip  = j["routes"][0]
            route = trip["geometry"]["coordinates"]
            order = stops
        else:
            trip  = j["trips"][0]
            route = trip["geometry"]["coordinates"]
            wps_out = j["waypoints"]
            ordered = sorted(zip(wps_out, stops), key=lambda x: x[0]["waypoint_index"])
            order   = [n for _, n in ordered]
        dur  = trip["duration"] / 60
        dist = trip["distance"] / 1000
        st.session_state.update({
            "routing":   route,
            "order":     order,
            "duration":  dur,
            "distance":  dist
        })
    else:
        st.error("⚠️ 경로 생성 실패: 입력을 확인하세요.")

# ────────────── 8. 지도 그리기 ──────────────
m = folium.Map(location=[clat, clon], zoom_start=12)

# 행정구역 경계 스타일
folium.GeoJson(
    boundary,
    name="행정구역 경계",
    style_function=lambda f: {
        "color":      "#2A9D8F",
        "weight":     3,
        "dashArray":  "5, 5",
        "fillColor":  "#2A9D8F",
        "fillOpacity":0.1
    }
).add_to(m)

# 전체 지점 클러스터
cluster = MarkerCluster().add_to(m)
for _, row in gdf.iterrows():
    folium.Marker([row.lat, row.lon], popup=row.name).add_to(cluster)

# 선택된 스톱 마커
for idx, (x, y) in enumerate(snapped, start=1):
    folium.Marker(
        [y, x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {st.session_state.get('order', stops)[idx-1]}"
    ).add_to(m)

# 경로 세그먼트 색상별 (스톱간)
if "routing" in st.session_state:
    route = st.session_state.routing
    # 정제: 스톱 좌표를 기준으로 인덱스 구하기
    indices = []
    for sx, sy in snapped:
        idx = min(range(len(route)),
                  key=lambda i: (route[i][0]-sx)**2 + (route[i][1]-sy)**2)
        indices.append(idx)
    # ensure start at 0, end at last
    indices[0] = 0
    indices[-1] = len(route) - 1

    colors = ["red", "orange", "green", "purple", "brown", "cadetblue"]
    for i in range(len(indices)-1):
        seg = route[indices[i]:indices[i+1]+1]
        folium.PolyLine(
            locations=[(pt[1], pt[0]) for pt in seg],
            color=colors[i % len(colors)],
            weight=6,
            opacity=0.8
        ).add_to(m)
        # 스톱간 순서 라벨 (중간)
        mid = seg[len(seg)//2]
        folium.map.Marker(
            [mid[1], mid[0]],
            icon=DivIcon(html=f"<div style='font-size:16px;color:{colors[i % len(colors)]}; font-weight:bold'>{i+1}</div>")
        ).add_to(m)
    # 자동 줌
    lats = [pt[1] for pt in route]
    lons = [pt[0] for pt in route]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)
