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

# ────────────── 0. Mapbox 토큰 (명확히 기입) ──────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ────────────── 1. 데이터 로드 ──────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 2. Streamlit UI ──────────────
st.set_page_config(layout="wide")
st.title("📍 청주시 경유지 최적 경로")

# 사이드바에 항상 고정되는 방문 순서 패널
with st.sidebar:
    st.header("🔢 최적 방문 순서")
    if "order" in st.session_state:
        for i, name in enumerate(st.session_state.order, 1):
            st.write(f"{i}. {name}")
    else:
        st.write("경로를 생성하세요.")

mode   = st.radio("🚗 이동 모드 선택", ["driving", "walking"], horizontal=True)
start  = st.selectbox("🏁 출발지 선택", gdf["name"].dropna().unique())
wps    = st.multiselect("🧭 경유지 선택",
                        [n for n in gdf["name"].dropna().unique() if n != start])

col1, col2 = st.columns([1,1])
with col1:
    btn_run   = st.button("✅ 최적 경로 찾기")
with col2:
    btn_clear = st.button("🚫 초기화")

dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2)
m1.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
m2.metric("📏 예상 이동 거리", f"{dist:.2f} km")

# ────────────── 3. 중심점 계산 ──────────────
ctr = boundary.geometry.centroid
clat, clon = ctr.y.mean(), ctr.x.mean()
if math.isnan(clat):
    clat, clon = 36.64, 127.48

# ────────────── 4. OSMnx 그래프 캐시 ──────────────
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
G     = load_graph(clat, clon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 5. 좌표 스냅 ──────────────
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
if btn_clear:
    for k in ["routing","order","duration","distance"]:
        st.session_state.pop(k, None)

# ────────────── 6. Mapbox API 호출 ──────────────
if btn_run and len(snapped) >= 2:
    coords = ";".join(f"{x},{y}" for x, y in snapped)
    if mode == "walking":
        url    = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords}"
        params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
        key    = "routes"
    else:
        url    = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords}"
        params = {
            "geometries":"geojson","overview":"full",
            "source":"first","destination":"last","roundtrip":"false",
            "access_token":MAPBOX_TOKEN
        }
        key    = "trips"
    r = requests.get(url, params=params); j = r.json()
    if r.status_code == 200 and j.get(key):
        if mode == "walking":
            t     = j["routes"][0]
            route = t["geometry"]["coordinates"]
            order = stops
        else:
            t       = j["trips"][0]
            route   = t["geometry"]["coordinates"]
            wouts   = j["waypoints"]
            vis     = sorted(zip(wouts, stops), key=lambda x: x[0]["waypoint_index"])
            order   = [n for _, n in vis]
        dur  = t["duration"]/60
        dist = t["distance"]/1000
        st.session_state.update({
            "routing":  route,
            "order":    order,
            "duration": dur,
            "distance": dist
        })
    else:
        st.error("⚠️ 경로 생성 실패: 입력을 확인해주세요.")

# ────────────── 7. 지도 그리기 ──────────────
m = folium.Map(location=[clat, clon], zoom_start=12)
folium.GeoJson(
    boundary,
    name="행정경계",
    style_function=lambda f: {
        "color":      "#2A9D8F",
        "weight":     3,
        "dashArray":  "5, 5",
        "fillColor":  "#2A9D8F",
        "fillOpacity":0.1
    }
).add_to(m)

cluster = MarkerCluster().add_to(m)
for _, r in gdf.iterrows():
    folium.Marker([r.lat, r.lon], popup=r.name).add_to(cluster)

# 선택 지점만 파란 마커
for idx, (x, y) in enumerate(snapped, start=1):
    folium.Marker(
        [y, x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {st.session_state.get('order', stops)[idx-1]}"
    ).add_to(m)

# 경로 세그먼트 색상별
if "routing" in st.session_state:
    rt     = st.session_state.routing
    colors = ["red","orange","green","purple","brown","cadetblue"]
    for i in range(len(rt)-1):
        seg = rt[i:i+2]
        folium.PolyLine(
            locations=[(p[1],p[0]) for p in seg],
            color=colors[i % len(colors)],
            weight=6,
            opacity=0.8
        ).add_to(m)
    # 자동 줌
    lats = [p[1] for p in rt]; lons = [p[0] for p in rt]
    m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)
