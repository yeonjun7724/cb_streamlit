import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests, math
from streamlit_folium import st_folium

# ───────────────────────────────────────────────────────────
# 1) 페이지 & 글로벌 CSS
# ───────────────────────────────────────────────────────────
st.set_page_config(page_title="청주시 경유지 최적 경로", layout="wide")
st.markdown("""
<style>
  /* 폰트 */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; background: #F9F9F9; color: #333; }
  h1 { font-weight:600; }
  /* 카드 */
  .card { background:#FFF; border-radius:12px; padding:20px; box-shadow:0 2px 6px rgba(0,0,0,0.1); margin-bottom:24px; }
  /* 버튼 */
  .stButton>button { border-radius:8px; font-weight:600; padding:10px 24px; }
  .btn-create { background: linear-gradient(90deg,#00C9A7,#008EAB); color:#FFF; }
  .btn-clear  { background:#E63946; color:#FFF; }
  .stButton>button:hover { opacity:0.9; }
  /* 입력 레이블 */
  label, .stRadio>label { color:#555; font-weight:500; }
  /* 지도 컨테이너 */
  .leaflet-container { border-radius:12px !important; box-shadow:0 2px 6px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ───────────────────────────────────────────────────────────
# 2) 데이터 로드
# ───────────────────────────────────────────────────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ───────────────────────────────────────────────────────────
# 3) 헤더
# ───────────────────────────────────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>📍 청주시 경유지 최적 경로</h1>", unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────
# 4) 메트릭 (전체 폭)
# ───────────────────────────────────────────────────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2, _ = st.columns([1,1,4], gap="small")

with m1:
    st.markdown("<div class='card text-center'>", unsafe_allow_html=True)
    st.markdown("<h4>⏱️ 예상 소요 시간</h4>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='margin-top:8px;'>{dur:.1f} 분</h2>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with m2:
    st.markdown("<div class='card text-center'>", unsafe_allow_html=True)
    st.markdown("<h4>📏 예상 이동 거리</h4>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='margin-top:8px;'>{dist:.2f} km</h2>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────
# 5) 레이아웃: 컨트롤 | 순서 | 지도
# ───────────────────────────────────────────────────────────
col_ctrl, col_order, col_map = st.columns([1.5,1,4], gap="large")

# --- 컨트롤 카드
with col_ctrl:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🚗 경로 설정")
    mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
    st.markdown("</div>", unsafe_allow_html=True)

    # 버튼
    create_clicked = st.button("✅ 경로 생성", key="run", help="최적 경로 계산", args=None, kwargs=None)
    clear_clicked  = st.button("🚫 초기화", key="clear")
    # 스타일 클래스 부여
    st.markdown("""<script>
      document.querySelectorAll('.stButton>button')[0].classList.add('btn-create');
      document.querySelectorAll('.stButton>button')[1].classList.add('btn-clear');
    </script>""", unsafe_allow_html=True)

# --- 순서 카드
with col_order:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🔢 방문 순서")
    if "order" in st.session_state:
        for i,name in enumerate(st.session_state.order,1):
            st.markdown(f"<p style='margin:4px 0;'><strong>{i}.</strong> {name}</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p style='color:#999;'>경로 생성 후 순서가 표시됩니다.</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# --- 지도
with col_map:
    # 중심 계산
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

    # OSMnx 캐시
    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    G     = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    # 스냅
    stops = [start] + wps
    snapped = []
    for nm in stops:
        r = gdf[gdf["name"]==nm].iloc[0]
        pt = Point(r.lon, r.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    # 초기화
    if clear_clicked:
        for k in ["segments","order","duration","distance"]:
            st.session_state.pop(k, None)

    # Mapbox API
    if create_clicked and len(snapped)>=2:
        segs, td, tl = [],0.0,0.0
        for i in range(len(snapped)-1):
            x1,y1 = snapped[i]; x2,y2 = snapped[i+1]
            coord = f"{x1},{y1};{x2},{y2}"
            if mode=="walking":
                url,key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}","routes"
                params={"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            else:
                url,key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}","trips"
                params={
                  "geometries":"geojson","overview":"full",
                  "source":"first","destination":"last","roundtrip":"false",
                  "access_token":MAPBOX_TOKEN
                }
            res = requests.get(url, params=params); data=res.json() if res.status_code==200 else {}
            if data.get(key):
                leg = data[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]; tl += leg["distance"]
        if segs:
            st.session_state.order    = stops
            st.session_state.duration = td/60
            st.session_state.distance = tl/1000
            st.session_state.segments = segs

    # 지도 렌더링
    st.markdown("<div class='card' style='padding:8px;'>", unsafe_allow_html=True)
    m = folium.Map(location=[clat,clon], zoom_start=12)
    folium.GeoJson(boundary, style_function=lambda f:{
        "color":"#26A69A","weight":2,"dashArray":"4,4","fillOpacity":0.05
    }).add_to(m)

    # 모든 포인트 (회색)
    mc = MarkerCluster().add_to(m)
    for _,row in gdf.iterrows():
        folium.Marker([row.lat,row.lon], popup=row.name,
                      icon=folium.Icon(color="gray", icon="info-sign")).add_to(mc)

    # 스톱 (파랑 플래그)
    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker([y,x],
            icon=folium.Icon(color="#008EAB",icon="flag"),
            tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)

    # 세그먼트 (뒤→앞)
    if "segments" in st.session_state:
        palette = ["#FF5252","#FFEA00","#69F0AE","#40C4FF","#E040FB","#FF8F00"]
        for i in range(len(st.session_state.segments),0,-1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine([(pt[1],pt[0]) for pt in seg],
                            color=palette[(i-1)%len(palette)],
                            weight=6, opacity=0.9
            ).add_to(m)
            mid = seg[len(seg)//2]
            folium.map.Marker([mid[1],mid[0]],
                icon=DivIcon(html=f"<div style='background:{palette[(i-1)%len(palette)]};"
                                  "color:#fff;border-radius:50%;width:28px;height:28px;"
                                  "line-height:28px;text-align:center;font-weight:600;'>"
                                  f"{i}</div>")
            ).add_to(m)
        # 자동 줌
        allpts = [pt for seg in st.session_state.segments for pt in seg]
        lats = [p[1] for p in allpts]; lons = [p[0] for p in allpts]
        m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
    else:
        m.location=[clat,clon]; m.zoom_start=12

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=650)
    st.markdown("</div>", unsafe_allow_html=True)
