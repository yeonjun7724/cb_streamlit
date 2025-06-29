import geopandas as gpd
import folium
from folium.plugins import MarkerCluster, BeautifyIcon
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
st.title("📍 청주시 경유지 최적 경로 (트렌디 포인트 & 컬러 세그먼트)")
mode = st.radio("🚗 이동 모드 선택:", ["driving", "walking"])

options = gdf["name"].dropna().unique().tolist()
c1, c2 = st.columns(2)
with c1:
    start = st.selectbox("🏁 출발지", options)
with c2:
    waypoints = st.multiselect("🧭 경유지", options)

# 선택된 순서
selected = []
if start: selected.append(start)
for wp in waypoints:
    if wp != start: selected.append(wp)

# ────────────── 3. 중심점 계산 ──────────────
centroid = boundary.geometry.centroid
center_lat = centroid.y.mean(); center_lon = centroid.x.mean()
if math.isnan(center_lat):
    center_lat, center_lon = 36.64, 127.48

# ────────────── 4. OSMnx 캐시 ──────────────
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

G = load_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 5. 스냅 좌표 계산 ──────────────
snapped = []
for name in selected:
    row = gdf[gdf["name"] == name].iloc[0]
    pt = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# ────────────── 6. 지도 생성 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
folium.GeoJson(boundary, style_function=lambda f: {
    "fillColor":"#fff","color":"#444","weight":2,"fillOpacity":0.05
}).add_to(m)

# — ① 전체 포인트 (클러스터)
all_cluster = MarkerCluster(name="전체 지점").add_to(m)
for _, r in gdf.iterrows():
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=5,
        color="#bbb",
        fill=True,
        fill_opacity=0.6
    ).add_to(all_cluster)

# — ② 선택된 점들 (트렌디 아이콘)
for i, (x, y) in enumerate(snapped, start=1):
    folium.Marker(
        location=[y, x],
        icon=BeautifyIcon(
            icon="map-pin",            # FontAwesome 아이콘
            icon_shape="marker",
            border_color="#333",
            text_color="#fff",
            background_color="#007bff" if i==1 else "#17a2b8",
            spin=False
        ),
        popup=f"{i}. {selected[i-1]}"
    ).add_to(m)

# — ③ 경로 그리기: 세그먼트별 색상 & 순서 라벨
colors = ["#e6194b","#3cb44b","#ffe119","#4363d8","#f58231","#911eb4"]
if "routing_result" in st.session_state:
    route = st.session_state["routing_result"]
    # 각 구간마다 색상 적용
    for idx in range(len(route)-1):
        seg = route[idx:idx+2]
        folium.PolyLine(
            locations=[(pt[1], pt[0]) for pt in seg],
            color=colors[idx % len(colors)],
            weight=6,
            opacity=0.8
        ).add_to(m)
        # 중간 라벨
        mid = seg[0] if len(seg)==2 else seg[len(seg)//2]
        folium.map.Marker(
            location=(mid[1], mid[0]),
            icon=DivIcon(html=f"""<div style="
                font-size:16px;
                color:{colors[idx % len(colors)]};
                font-weight:bold;
                text-shadow:1px 1px 2px #fff;
            ">{idx+1}</div>""")
        ).add_to(m)

# — 자동 줌
if "routing_result" in st.session_state:
    pts = st.session_state["routing_result"]
    lats = [p[1] for p in pts]; lons = [p[0] for p in pts]
    m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
elif snapped:
    ys = [p[1] for p in snapped]; xs = [p[0] for p in snapped]
    m.fit_bounds([[min(ys),min(xs)],[max(ys),max(xs)]])
else:
    b = gdf.total_bounds  # [minx,miny,maxx,maxy]
    m.fit_bounds([[b[1],b[0]],[b[3],b[2]]])

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)

# ────────────── 7. 메트릭 & 순서 표시 ──────────────
if "ordered_names" in st.session_state:
    st.subheader("🔢 최적 방문 순서")
    for i, nm in enumerate(st.session_state["ordered_names"], 1):
        st.write(f"{i}. {nm}")
    st.metric("⏱️ 예상 소요 시간", f"{st.session_state['duration']:.1f} 분")
    st.metric("📏 예상 이동 거리", f"{st.session_state['distance']:.2f} km")

# ────────────── 8. 버튼 로직 ──────────────
colA, colB = st.columns(2)
with colA:
    if st.button("✅ 최적 경로 찾기"):
        if len(snapped) < 2:
            st.warning("⚠️ 출발지/경유지 2개 이상 선택해주세요!"); st.stop()
        coords = ";".join(f"{x},{y}" for x,y in snapped)
        if mode=="walking":
            url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords}"
            params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            key="routes"
        else:
            url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords}"
            params = {
                "geometries":"geojson","overview":"full",
                "source":"first","destination":"last","roundtrip":"false",
                "access_token":MAPBOX_TOKEN
            }
            key="trips"
        r = requests.get(url, params=params); j=r.json()
        if r.status_code!=200 or not j.get(key):
            st.error("❌ 경로 생성 실패"); st.stop()
        if mode=="walking":
            tr=j["routes"][0]; route=tr["geometry"]["coordinates"]
            dur, dist = tr["duration"]/60, tr["distance"]/1000
            order = selected
        else:
            tr=j["trips"][0]; route=tr["geometry"]["coordinates"]
            dur, dist = tr["duration"]/60, tr["distance"]/1000
            wps=j["waypoints"]
            vis=sorted(zip(wps, selected), key=lambda x:x[0]["waypoint_index"])
            order=[n for _,n in vis]
        st.session_state.update({
            "routing_result": route,
            "ordered_names": order,
            "duration": dur,
            "distance": dist
        })
        st.success("✅ 최적 경로 생성됨!"); st.rerun()
with colB:
    if st.button("🚫 초기화"):
        for k in ["routing_result","ordered_names","duration","distance"]:
            st.session_state.pop(k, None)
        st.rerun()
