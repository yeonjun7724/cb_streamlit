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

st.set_page_config(layout="wide")
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# 1. 데이터 불러오기
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# 2. 사이드바에 고정된 순서 표시
with st.sidebar:
    st.header("🔢 최적 방문 순서")
    if "order" in st.session_state:
        for i, nm in enumerate(st.session_state.order, 1):
            st.write(f"{i}. {nm}")
    else:
        st.write("경로를 생성하세요.")

# 3. UI 컨트롤
st.title("📍 청주시 경유지 최적 경로")
mode   = st.radio("🚗 이동 모드", ["driving","walking"], horizontal=True)
start  = st.selectbox("🏁 출발지", gdf["name"].dropna().unique())
wps    = st.multiselect("🧭 경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
run    = st.button("✅ 최적 경로 찾기")
clear  = st.button("🚫 초기화")

# 4. 상단 메트릭
dur  = st.session_state.get("duration",0.0)
dist = st.session_state.get("distance",0.0)
c1,c2 = st.columns(2)
c1.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
c2.metric("📏 예상 이동 거리", f"{dist:.2f} km")

# 5. 중심 좌표 계산
ctr = boundary.geometry.centroid
clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
if math.isnan(clat):
    clat, clon = 36.64, 127.48

# 6. OSMnx 그래프
@st.cache_data
def load_graph(lat, lon):
    return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
G     = load_graph(clat, clon)
edges = ox.graph_to_gdfs(G, nodes=False)

# 7. 스톱 스냅
stops   = [start] + wps
snapped = []
for name in stops:
    row = gdf[gdf["name"]==name].iloc[0]
    pt  = Point(row.lon, row.lat)
    edges["d"] = edges.geometry.distance(pt)
    ln = edges.loc[edges["d"].idxmin()]
    sp = ln.geometry.interpolate(ln.geometry.project(pt))
    snapped.append((sp.x, sp.y))

# 8. 초기화
if clear:
    for k in ["segments","order","duration","distance"]:
        st.session_state.pop(k, None)

# 9. Mapbox API 호출 (구간별)
if run and len(snapped)>=2:
    segs = []; total_d=0; total_l=0
    for i in range(len(snapped)-1):
        x1,y1 = snapped[i]; x2,y2 = snapped[i+1]
        coord = f"{x1},{y1};{x2},{y2}"
        if mode=="walking":
            url   = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}"
            params= {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            key   = "routes"
        else:
            url   = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}"
            params= {
                "geometries":"geojson","overview":"full",
                "source":"first","destination":"last","roundtrip":"false",
                "access_token":MAPBOX_TOKEN
            }
            key   = "trips"
        r = requests.get(url, params=params); j=r.json()
        if r.status_code==200 and j.get(key):
            leg = j[key][0]
            segs.append(leg["geometry"]["coordinates"])
            total_d += leg["duration"]
            total_l += leg["distance"]
        else:
            st.error("⚠️ 경로 생성 실패"); segs=[]
            break
    if segs:
        st.session_state.segments = segs
        st.session_state.order    = stops
        st.session_state.duration = total_d/60
        st.session_state.distance = total_l/1000

# 10. 지도 그리기
m = folium.Map(location=[clat,clon], zoom_start=12)

# 행정경계 스타일
folium.GeoJson(
    boundary,
    name="행정경계",
    style_function=lambda f: {
        "color":"#2A9D8F","weight":3,"dashArray":"5,5",
        "fillColor":"#2A9D8F","fillOpacity":0.1
    }
).add_to(m)

# 전체 포인트
cluster = MarkerCluster().add_to(m)
for _,r in gdf.iterrows():
    folium.Marker([r.lat,r.lon],popup=r.name).add_to(cluster)

# 스톱 마커
for idx,(x,y) in enumerate(snapped,1):
    folium.Marker(
        [y,x],
        icon=folium.Icon(color="blue"),
        tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
    ).add_to(m)

# 구간별 PolyLine + 숫자 라벨 (강화된 스타일)
if "segments" in st.session_state:
    colors = ["#e6194b","#3cb44b","#ffe119","#4363d8","#f58231","#911eb4"]
    for i, seg in enumerate(st.session_state.segments,1):
        folium.PolyLine(
            locations=[(pt[1],pt[0]) for pt in seg],
            color=colors[(i-1)%len(colors)],
            weight=6, opacity=0.8
        ).add_to(m)
        # 숫자 라벨을 더 도드라지게
        mid = seg[len(seg)//2]
        html = f"""
        <div style="
            background: rgba(255,255,255,0.9);
            border: 2px solid {colors[(i-1)%len(colors)]};
            border-radius: 50%;
            width:28px; height:28px;
            line-height:28px;
            text-align:center;
            font-size:16px;
            font-weight:bold;
            color:{colors[(i-1)%len(colors)]};
        ">{i}</div>
        """
        folium.map.Marker([mid[1],mid[0]], icon=DivIcon(html=html)).add_to(m)

    # 자동 줌
    all_pts = [pt for seg in st.session_state.segments for pt in seg]
    lats, lons = [p[1] for p in all_pts], [p[0] for p in all_pts]
    m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])

    # 11. **범례(Legend)** 추가
    legend_html = """
      <div style="
        position: fixed; 
        bottom: 50px; left: 50px; 
        background: white; 
        padding: 10px; 
        border: 2px solid gray; 
        z-index:9999;
        font-size:14px;
      ">
        <b>경로 범례</b><br>
        <div style="display:flex;align-items:center;margin:4px 0;">
          <span style="background:#e6194b;width:12px;height:12px;display:inline-block;margin-right:6px;"></span>
          1. {st.session_state.order[0]} → {st.session_state.order[1]}
        </div>
        <div style="display:flex;align-items:center;margin:4px 0;">
          <span style="background:#3cb44b;width:12px;height:12px;display:inline-block;margin-right:6px;"></span>
          2. {st.session_state.order[1]} → {st.session_state.order[2] if len(st.session_state.order)>2 else ''}
        </div>
        <!-- 필요 시 더 추가 -->
      </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
else:
    # 아직 경로 없으면 출발지로 줌인
    sx, sy = snapped[0]
    m.location = [sy, sx]
    m.zoom_start = 15

folium.LayerControl().add_to(m)
st_folium(m, width=800, height=600)
