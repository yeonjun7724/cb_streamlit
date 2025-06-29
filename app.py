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
gdf    = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── 2. Streamlit UI ──────────────
st.title("📍 청주시 경유지 최적 경로")
mode   = st.radio("🚗 이동 모드 선택", ["driving", "walking"], horizontal=True)
start  = st.selectbox("🏁 출발지 선택", gdf["name"].dropna().unique())
wps    = st.multiselect("🧭 경유지 선택",
                        [n for n in gdf["name"].dropna().unique() if n != start])

# 고정 버튼 & 메트릭
col1, col2 = st.columns([1,1])
with col1:
    find  = st.button("✅ 최적 경로 찾기")
with col2:
    reset = st.button("🚫 초기화")
dur = st.session_state.get("duration", 0.0)
dist= st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2)
m1.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
m2.metric("📏 예상 이동 거리", f"{dist:.2f} km")

# ────────────── 3. 중심점 계산 ──────────────
ctr = boundary.geometry.centroid
center_lat, center_lon = ctr.y.mean(), ctr.x.mean()
if math.isnan(center_lat): center_lat, center_lon = 36.64, 127.48

# ────────────── 4. OSMnx 그래프 캐시 ──────────────
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
G     = load_graph(center_lat, center_lon)
edges = ox.graph_to_gdfs(G, nodes=False)

# ────────────── 5. 좌표 스냅 ──────────────
selected = [start] + wps
snapped  = []
for name in selected:
    row = gdf[gdf["name"]==name].iloc[0]
    pt  = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# 초기화
if reset:
    for k in ["routing","order","duration","distance"]:
        st.session_state.pop(k, None)

# ────────────── 6. Mapbox 호출 ──────────────
if find and len(snapped)>=2:
    coords = ";".join(f"{x},{y}" for x,y in snapped)
    if mode=="walking":
        url   = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords}"
        params= {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
        key   = "routes"
    else:
        url   = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords}"
        params= {
            "geometries":"geojson","overview":"full",
            "source":"first","destination":"last","roundtrip":"false",
            "access_token":MAPBOX_TOKEN
        }
        key   = "trips"
    r = requests.get(url, params=params)
    j = r.json()
    if r.status_code==200 and j.get(key):
        if mode=="walking":
            t  = j["routes"][0]
            route = t["geometry"]["coordinates"]
            order = selected
        else:
            t  = j["trips"][0]
            route = t["geometry"]["coordinates"]
            wps_out = j["waypoints"]
            vis = sorted(zip(wps_out, selected), key=lambda x:x[0]["waypoint_index"])
            order = [n for _,n in vis]
        dur  = t["duration"]/60
        dist = t["distance"]/1000
        st.session_state.update({
            "routing":   route,
            "order":     order,
            "duration":  dur,
            "distance":  dist
        })
    else:
        st.error("경로 생성 실패: 입력을 확인해주세요.")

# ────────────── 7. 지도 그리기 ──────────────
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
# 행정경계 강조
folium.GeoJson(
    boundary,
    name="행정경계",
    style_function=lambda f: {
        "color": "#1f77b4",
        "weight": 3,
        "fillOpacity": 0
    }
).add_to(m)

# 모든 지점 클러스터
cluster = MarkerCluster(name="전체 지점").add_to(m)
for _, r in gdf.iterrows():
    folium.Marker([r.lat, r.lon], popup=r.name).add_to(cluster)

# 선택된 지점 표시 (기본 마커 색상만 파랑)
for idx, (x,y) in enumerate(snapped, start=1):
    folium.Marker(
        [y,x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {selected[idx-1]}"
    ).add_to(m)

# 경로 세그먼트만 색상별로, 숫자 레이블
colors = ["red","orange","green","purple","brown","cadetblue"]
if "routing" in st.session_state:
    rt = st.session_state.routing
    for i in range(len(rt)-1):
        seg = rt[i:i+2]
        folium.PolyLine(
            locations=[(p[1],p[0]) for p in seg],
            color=colors[i % len(colors)],
            weight=6,
            opacity=0.9
        ).add_to(m)
        # 경로 위에 순서 레이블 (한 번만)
        mid_lon = (seg[0][0] + seg[1][0]) / 2
        mid_lat = (seg[0][1] + seg[1][1]) / 2
        folium.map.Marker(
            [mid_lat, mid_lon],
            icon=DivIcon(html=f"""<div style="
                font-size:14px;
                color:{colors[i % len(colors)]};
                font-weight:bold;
            ">{i+1}</div>""")
        ).add_to(m)
    # 자동 줌
    pts = st.session_state.routing
    lats = [p[1] for p in pts]; lons = [p[0] for p in pts]
    m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)

# ────────────── 8. 순서 출력 ──────────────
if "order" in st.session_state:
    st.subheader("🔢 최적 방문 순서")
    for i, name in enumerate(st.session_state.order, 1):
        st.write(f"{i}. {name}")
