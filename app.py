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
# 1. 페이지 설정 & 전역 CSS
# ───────────────────────────────────────────────────────────
st.set_page_config(page_title="청주시 경유지 최적 경로", layout="wide")
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700&display=swap');
  html, body, [class*="css"] { font-family: 'Nanum Gothic', sans-serif; background: #F0F2F5; color: #202124; }
  h1, h2, h3, h4 { margin: 0; padding: 0; }

  /* 레이아웃 그리드 */
  .full-width { width: 100% !important; }
  .card { background: #ffffff; border-radius:16px; box-shadow:0 4px 12px rgba(0,0,0,0.08); padding:24px; margin-bottom:24px; }
  .btn-primary {
    background: linear-gradient(90deg, #3DB5FF, #2A8DFF);
    color: white !important;
    font-weight:700;
    border:none; border-radius:8px;
    padding:12px 24px;
    transition: transform .1s;
  }
  .btn-primary:hover { transform: translateY(-2px); opacity:0.9; }
  .btn-secondary {
    background: #FF5A5F; color: white !important;
    font-weight:700; border:none; border-radius:8px;
    padding:12px 24px;
    transition: transform .1s;
  }
  .btn-secondary:hover { transform: translateY(-2px); opacity:0.9; }

  /* 입력 라벨 컬러 */
  label, .stRadio>label { color: #5F6368 !important; }
  /* 레이어 컨트롤 위치 (네이버맵 느낌) */
  .leaflet-top.leaflet-left { top: 10px; left: 10px; }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1..."

# ───────────────────────────────────────────────────────────
# 2. 데이터 로드
# ───────────────────────────────────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ───────────────────────────────────────────────────────────
# 3. 헤더
# ───────────────────────────────────────────────────────────
st.markdown("""
<div class="card full-width" style="text-align:center;">
  <h1>📍 청주시 경유지 최적 경로</h1>
  <p style="color:#5F6368; margin-top:4px;">네이버·카카오 감성의 트렌디 대시보드</p>
</div>
""", unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────
# 4. 메트릭
# ───────────────────────────────────────────────────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2, _ = st.columns([1,1,4], gap="small")
with m1:
    st.markdown(f"""
    <div class="card">
      <h4>⏱️ 예상 소요 시간</h4>
      <h2 style="margin-top:8px;">{dur:.1f} 분</h2>
    </div>
    """, unsafe_allow_html=True)
with m2:
    st.markdown(f"""
    <div class="card">
      <h4>📏 예상 이동 거리</h4>
      <h2 style="margin-top:8px;">{dist:.2f} km</h2>
    </div>
    """, unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────
# 5. 메인 레이아웃 (컨트롤 / 순서 / 지도)
# ───────────────────────────────────────────────────────────
col_ctrl, col_map = st.columns([1.5,4], gap="large")

with col_ctrl:
    # 경로 설정 카드
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🚗 경로 설정")
    mode  = st.radio("", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
    st.markdown("</div>", unsafe_allow_html=True)

    # 버튼
    st.markdown("<div style='display:flex; gap:12px;'>", unsafe_allow_html=True)
    st.markdown("<button class='btn-primary'>✅ 경로 생성</button>", unsafe_allow_html=True)
    st.markdown("<button class='btn-secondary'>🚫 초기화</button>", unsafe_allow_html=True)
    st.markdown("</div><br>", unsafe_allow_html=True)

    # 방문 순서 카드
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🔢 방문 순서")
    if "order" in st.session_state:
        for i, nm in enumerate(st.session_state.order,1):
            st.markdown(f"<p style='margin:4px 0;'><strong>{i}.</strong> {nm}</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p style='color:#9E9E9E;'>아직 경로가 없습니다.</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_map:
    # 중심점
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

    # 그래프 캐시
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

    # Mapbox API
    if st.button("dummy"): pass  # 실제 버튼 로직은 js로 바인딩 필요

    # 지도 카드
    st.markdown("<div class='card' style='padding:8px;'>", unsafe_allow_html=True)
    m = folium.Map(location=[clat,clon], zoom_start=12)
    folium.GeoJson(boundary, style_function=lambda f:{
        "color":"#26A69A","weight":2,"dashArray":"5,5","fillOpacity":0.05
    }).add_to(m)
    mc = MarkerCluster().add_to(m)
    for _,r in gdf.iterrows():
        folium.Marker([r.lat,r.lon], popup=r.name,
                      icon=folium.Icon(color="gray")).add_to(mc)
    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker([y,x],
                      icon=folium.Icon(color="#2962FF",icon="flag"),
                      tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)
    if "segments" in st.session_state:
        palette = ["#FF5252","#FFEA00","#69F0AE","#40C4FF","#E040FB","#FF8F00"]
        for i in range(len(st.session_state.segments),0,-1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine(
                [(pt[1],pt[0]) for pt in seg],
                color=palette[(i-1)%len(palette)], weight=6, opacity=0.9
            ).add_to(m)
            mid = seg[len(seg)//2]
            folium.map.Marker([mid[1],mid[0]],
                icon=DivIcon(html=f"<div style='background:{palette[(i-1)%len(palette)]};"
                                  "color:#fff;border-radius:50%;width:28px;height:28px;"
                                  "line-height:28px;text-align:center;font-weight:600;'>{i}</div>")
            ).add_to(m)
        allpts = [pt for seg in st.session_state.segments for pt in seg]
        lats = [p[1] for p in allpts]; lons = [p[0] for p in allpts]
        m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
    else:
        m.location=[clat,clon]; m.zoom_start=12

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=650)
    st.markdown("</div>", unsafe_allow_html=True)
