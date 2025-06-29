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

# ────────────── 1. 데이터 로드 ──────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 2. Streamlit UI ──────────────
st.title("📍 청주시 경유지 최적 경로 (안전 캐시 버전)")
mode = st.radio("🚗 이동 모드 선택:", ["driving", "walking"])

options = gdf["name"].dropna().unique().tolist()
col1, col2 = st.columns(2)
with col1:
    start = st.selectbox("🏁 출발지 선택", options)
with col2:
    waypoints = st.multiselect("🧭 경유지 선택", options)

selected_names = []
if start:
    selected_names.append(start)
for wp in waypoints:
    if wp != start:
        selected_names.append(wp)

# ────────────── 3. 중심점 계산 ──────────────
center_lat = boundary.geometry.centroid.y.mean()
center_lon = boundary.geometry.centroid.x.mean()
if math.isnan(center_lat) or math.isnan(center_lon):
    center_lat, center_lon = 36.64, 127.48

# ────────────── 4. OSMnx 그래프 캐시 ──────────────
@st.cache_data
def get_osm_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

G = get_osm_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 5. Nearest 스냅 (내부 계산) ──────────────
snapped = []
if selected_names:
    for name in selected_names:
        row = gdf[gdf["name"] == name].iloc[0]
        pt = Point(row["lon"], row["lat"])
        edges["dist"] = edges.distance(pt)
        nl = edges.loc[edges["dist"].idxmin()]
        sp = nl.geometry.interpolate(nl.geometry.project(pt))
        snapped.append((sp.x, sp.y))

# ────────────── 6. Folium 지도 생성 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
folium.GeoJson(boundary, style_function=lambda x: {
    "fillColor":"#fff","color":"#000","weight":1,"fillOpacity":0.1
}).add_to(m)

# — ① 전체 투어 지점 클러스터 (회색)
all_cluster = MarkerCluster(name="All Tour Points").add_to(m)
for _, r in gdf.iterrows():
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=4,
        color="lightgray",
        fill=True,
        fill_opacity=0.7,
        popup=r.name
    ).add_to(all_cluster)

# — ② 선택된 출발지/경유지 (파란색)
for x, y in snapped:
    folium.CircleMarker(
        location=[y, x],
        radius=6,
        color="blue",
        fill=True,
        fill_opacity=1
    ).add_to(m)

# — ③ Polyline: 각 구간별 색상 & 순서 표시
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    order = st.session_state["ordered_names"]
    # 각 순서별 좌표 리스트
    coords = snapped.copy()
    # 좌표 순서 보정
    if len(order) == len(selected_names):
        # nothing to change
        pass
    # 색상 팔레트 (필요 시 확장)
    colors = ["red","orange","green","purple","brown","cadetblue"]
    for i in range(len(coords)-1):
        a = coords[i]
        b = coords[i+1]
        # Directions API로 분할 경로
        u = f"{a[0]},{a[1]};{b[0]},{b[1]}"
        url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{u}"
        params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
        res = requests.get(url, params=params).json()
        leg = res["routes"][0]["geometry"]["coordinates"]
        col = colors[i % len(colors)]
        folium.PolyLine(leg, color=col, weight=5).add_to(m)
        # 중간에 순서 텍스트
        mid = leg[len(leg)//2]
        folium.map.Marker(
            location=[mid[1], mid[0]],
            icon=DivIcon(html=f"<div style='font-size:14px;color:{col};'><b>{i+1}</b></div>")
        ).add_to(m)

# — ④ 자동 줌
if "routing_result" in st.session_state:
    pts = st.session_state["routing_result"]
    lats = [p[1] for p in pts]; lons = [p[0] for p in pts]
    m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
elif snapped:
    ys = [p[1] for p in snapped]; xs = [p[0] for p in snapped]
    m.fit_bounds([[min(ys),min(xs)],[max(ys),max(xs)]])
else:
    minx,miny,maxx,maxy = gdf.total_bounds
    m.fit_bounds([[miny,minx],[maxy,maxx]])

folium.LayerControl().add_to(m)
st_folium(m, height=600, width=800)

# ────────────── 7. 메트릭: 순서, 시간·거리 ──────────────
if "ordered_names" in st.session_state:
    st.subheader("🔢 최적 방문 순서")
    for idx, nm in enumerate(st.session_state["ordered_names"], 1):
        st.write(f"{idx}. {nm}")
    st.metric("⏱️ 예상 소요 시간", f"{st.session_state['duration']:.1f} 분")
    st.metric("📏 예상 이동 거리", f"{st.session_state['distance']:.2f} km")

# ────────────── 8. 버튼 로직 ──────────────
col1, col2 = st.columns(2)
with col1:
    if st.button("✅ 최적 경로 찾기"):
        if len(snapped) < 2:
            st.warning("⚠️ 출발지/경유지 2개 이상 선택해주세요!"); st.stop()
        s = ";".join(f"{x},{y}" for x,y in snapped)
        if mode == "walking":
            url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{s}"
            params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            key="routes"
        else:
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{s}"
            params = {
                "geometries":"geojson","overview":"full",
                "source":"first","destination":"last","roundtrip":"false","access_token":MAPBOX_TOKEN
            }
            key="trips"
        r = requests.get(url, params=params); j=r.json()
        if r.status_code!=200 or not j.get(key):
            st.error("❌ 경로 생성 실패"); st.stop()
        if mode=="walking":
            tr=j["routes"][0]; route=tr["geometry"]["coordinates"]
            duration,dist = tr["duration"]/60, tr["distance"]/1000
            order = selected_names
        else:
            tr=j["trips"][0]; route=tr["geometry"]["coordinates"]
            duration,dist = tr["duration"]/60, tr["distance"]/1000
            wps=j["waypoints"]
            vis=sorted(zip(wps, selected_names), key=lambda x:x[0]["waypoint_index"])
            order=[n for _,n in vis]
        st.session_state.update({
            "routing_result": route,
            "ordered_names": order,
            "duration": duration,
            "distance": dist
        })
        st.success("✅ 최적 경로 생성됨!"); st.rerun()
with col2:
    if st.button("🚫 초기화"):
        for k in ["routing_result","ordered_names","duration","distance"]:
            st.session_state.pop(k, None)
        st.rerun()
