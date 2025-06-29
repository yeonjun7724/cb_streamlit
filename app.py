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

# ────────────── Page Config ──────────────
st.set_page_config(layout="wide")

# ────────────── 0. Mapbox Token ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ────────────── 1. Load Data ──────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── Sidebar: Fixed Order ──────────────
with st.sidebar:
    st.header("🔢 최적 방문 순서")
    if "order" in st.session_state:
        for i, name in enumerate(st.session_state.order, 1):
            st.write(f"{i}. {name}")
    else:
        st.write("경로를 생성하세요.")

# ────────────── 2. UI Controls ──────────────
st.title("📍 청주시 경유지 최적 경로")
mode  = st.radio("🚗 이동 모드 선택", ["driving", "walking"], horizontal=True)
start = st.selectbox("🏁 출발지 선택", gdf["name"].dropna().unique())
wps   = st.multiselect("🧭 경유지 선택", [n for n in gdf["name"].dropna().unique() if n != start])

col_run, col_clear = st.columns(2)
with col_run:
    run   = st.button("✅ 최적 경로 찾기")
with col_clear:
    clear = st.button("🚫 초기화")

# ────────────── 3. Fixed Metrics ──────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2)
m1.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
m2.metric("📏 예상 이동 거리", f"{dist:.2f} km")

# ────────────── 4. Compute Center ──────────────
ctr        = boundary.geometry.centroid
center_lat = float(ctr.y.mean()); center_lon = float(ctr.x.mean())
if math.isnan(center_lat):
    center_lat, center_lon = 36.64, 127.48

# ────────────── 5. OSMnx Graph Cache ──────────────
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
G     = load_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 6. Snap Stops ──────────────
stops   = [start] + wps
snapped = []
for name in stops:
    row = gdf[gdf["name"] == name].iloc[0]
    pt  = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# ────────────── 7. Clear ──────────────
if clear:
    for k in ["segments", "order", "duration", "distance"]:
        st.session_state.pop(k, None)

# ────────────── 8. Call Mapbox for Each Leg ──────────────
if run and len(snapped) >= 2:
    segments = []
    total_dur = 0.0
    total_dist = 0.0
    for i in range(len(snapped) - 1):
        x1, y1 = snapped[i]
        x2, y2 = snapped[i + 1]
        coord_str = f"{x1},{y1};{x2},{y2}"
        if mode == "walking":
            url    = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord_str}"
            params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}
            key    = "routes"
        else:
            url    = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord_str}"
            params = {
                "geometries": "geojson", "overview": "full",
                "source": "first", "destination": "last", "roundtrip": "false",
                "access_token": MAPBOX_TOKEN
            }
            key    = "trips"
        r = requests.get(url, params=params)
        j = r.json()
        if r.status_code == 200 and j.get(key):
            leg = j[key][0]
            segments.append(leg["geometry"]["coordinates"])
            total_dur  += leg["duration"]
            total_dist += leg["distance"]
        else:
            st.error("⚠️ 경로 생성 실패: 입력을 확인해주세요.")
            segments = []
            break
    if segments:
        st.session_state.order    = stops
        st.session_state.duration = total_dur / 60
        st.session_state.distance = total_dist / 1000
        st.session_state.segments = segments

# ────────────── 9. Draw Map ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

# 행정경계 스타일
folium.GeoJson(
    boundary,
    name="행정경계",
    style_function=lambda f: {
        "color": "#2A9D8F", "weight": 3, "dashArray": "5,5",
        "fillColor": "#2A9D8F", "fillOpacity": 0.1
    }
).add_to(m)

# 전체 지점 클러스터 (회색)
cluster = MarkerCluster().add_to(m)
for _, r in gdf.iterrows():
    folium.Marker(
        [r.lat, r.lon],
        popup=r.name,
        icon=folium.Icon(color="gray")
    ).add_to(cluster)

# 선택된 스톱 마커 (파란색)
for idx, (x, y) in enumerate(snapped, 1):
    folium.Marker(
        [y, x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {st.session_state.get('order', stops)[idx-1]}"
    ).add_to(m)

# 세그먼트 그리기 & 스타일 숫자 라벨
if "segments" in st.session_state:
    colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4"]
    segs = st.session_state.segments
    # 낮은 순서가 위로 오도록, 뒤에서부터 그리기
    for i in range(len(segs), 0, -1):
        seg = segs[i - 1]
        folium.PolyLine(
            locations=[(pt[1], pt[0]) for pt in seg],
            color=colors[(i-1) % len(colors)],
            weight=6, opacity=0.8
        ).add_to(m)
        mid = seg[len(seg) // 2]
        html = f"""
        <div style="
            background: {colors[(i-1)%len(colors)]};
            color: white;
            border-radius: 50%;
            width:24px; height:24px;
            line-height:24px;
            text-align:center;
            font-size:14px;
            font-weight:bold;
            box-shadow: 1px 1px 4px rgba(0,0,0,0.4);
        ">{i}</div>
        """
        folium.map.Marker([mid[1], mid[0]], icon=DivIcon(html=html)).add_to(m)
    # 자동 줌
    all_pts = [pt for seg in segs for pt in seg]
    lats = [p[1] for p in all_pts]; lons = [p[0] for p in all_pts]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
else:
    # no route: zoom to start
    sx, sy = snapped[0]
    m.location = [sy, sx]
    m.zoom_start = 15

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)
