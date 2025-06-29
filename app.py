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
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── Sidebar: Fixed Order Display ──────────────
with st.sidebar:
    st.header("🔢 최적 방문 순서")
    if "order" in st.session_state:
        for i, name in enumerate(st.session_state.order, 1):
            st.write(f"{i}. {name}")
    else:
        st.write("경로를 생성하세요.")

# ────────────── 2. UI Controls ──────────────
st.title("📍 청주시 경유지 최적 경로")
mode = st.radio("🚗 이동 모드 선택", ["driving", "walking"], horizontal=True)
start = st.selectbox("🏁 출발지 선택", gdf["name"].dropna().unique())
wps = st.multiselect("🧭 경유지 선택",
                     [n for n in gdf["name"].dropna().unique() if n != start])

col_run, col_clear = st.columns(2)
with col_run:
    run = st.button("✅ 최적 경로 찾기")
with col_clear:
    clear = st.button("🚫 초기화")

# ────────────── 3. Fixed Metrics Display ──────────────
dur = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2)
m1.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
m2.metric("📏 예상 이동 거리", f"{dist:.2f} km")

# ────────────── 4. Compute Center ──────────────
ctr = boundary.geometry.centroid
clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
if math.isnan(clat):
    clat, clon = 36.64, 127.48

# ────────────── 5. OSMnx Graph Cache ──────────────
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

G = load_graph(clat, clon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 6. Snap Coordinates ──────────────
stops = [start] + wps
snapped = []
for name in stops:
    row = gdf[gdf["name"] == name].iloc[0]
    pt = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# ────────────── Clear Session ──────────────
if clear:
    for key in ["segments", "order", "duration", "distance"]:
        st.session_state.pop(key, None)

# ────────────── 7. Mapbox Calls for Each Leg ──────────────
if run and len(snapped) >= 2:
    segments = []
    total_dur = 0.0
    total_dist = 0.0
    for i in range(len(snapped) - 1):
        ox, oy = snapped[i]
        dx, dy = snapped[i + 1]
        coord_str = f"{ox},{oy};{dx},{dy}"
        if mode == "walking":
            url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord_str}"
            params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}
            key = "routes"
        else:
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord_str}"
            params = {
                "geometries": "geojson",
                "overview": "full",
                "source": "first",
                "destination": "last",
                "roundtrip": "false",
                "access_token": MAPBOX_TOKEN
            }
            key = "trips"
        resp = requests.get(url, params=params)
        data = resp.json()
        if resp.status_code == 200 and data.get(key):
            leg = data[key][0]
            coords = leg["geometry"]["coordinates"]
            segments.append(coords)
            total_dur += leg["duration"]
            total_dist += leg["distance"]
        else:
            st.error("⚠️ 경로 생성 실패: 입력을 확인하세요.")
            segments = []
            break

    if segments:
        st.session_state.segments = segments
        st.session_state.order = stops
        st.session_state.duration = total_dur / 60
        st.session_state.distance = total_dist / 1000

# ────────────── 8. Draw Map ──────────────
m = folium.Map(location=[clat, clon], zoom_start=12)

# Boundary style
folium.GeoJson(
    boundary,
    name="행정구역 경계",
    style_function=lambda f: {
        "color": "#2A9D8F",
        "weight": 3,
        "dashArray": "5, 5",
        "fillOpacity": 0.1
    }
).add_to(m)

# All points clustering
cluster = MarkerCluster().add_to(m)
for _, row in gdf.iterrows():
    folium.Marker([row.lat, row.lon], popup=row.name).add_to(cluster)

# Stop markers with numbers
for idx, (x, y) in enumerate(snapped, start=1):
    folium.Marker(
        [y, x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {st.session_state.get('order', stops)[idx-1]}"
    ).add_to(m)

# Segment polylines with distinct colors
if "segments" in st.session_state:
    colors = ["red", "orange", "green", "purple", "brown", "cadetblue"]
    for i, seg in enumerate(st.session_state.segments):
        folium.PolyLine(
            locations=[(pt[1], pt[0]) for pt in seg],
            color=colors[i % len(colors)],
            weight=6,
            opacity=0.8
        ).add_to(m)
    # fit bounds to whole route
    all_coords = [pt for seg in st.session_state.segments for pt in seg]
    lats = [p[1] for p in all_coords]; lons = [p[0] for p in all_coords]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)
