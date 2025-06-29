import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests, math
from streamlit_folium import st_folium

# ──────────────────────────────────────────────
# 1) 페이지 & CSS
# ──────────────────────────────────────────────
st.set_page_config(page_title="청주시 경유지 최적 경로", layout="wide")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif; background: #F9F9F9; color: #333;
  }
  h1 { font-weight:700; }
  h4 { font-weight:600; }
  .card {
    background: linear-gradient(135deg, #FFFFFF 0%, #F6F8FA 100%);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    margin-bottom: 24px;
  }
  .card:hover {
    transform: translateY(-4px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.12);
  }
  .stButton>button {
    border: none;
    border-radius: 8px;
    font-weight:600;
    padding: 12px 24px;
    transition: all 0.2s ease-in-out;
  }
  .stButton>button:hover {
    opacity: 0.85;
    transform: translateY(-2px);
  }
  .btn-create {
    background: linear-gradient(90deg,#00C9A7,#008EAB); color:#FFF;
  }
  .btn-clear  {
    background:#E63946; color:#FFF;
  }
  .leaflet-container {
    border-radius:12px !important;
    box-shadow:0 2px 6px rgba(0,0,0,0.1);
  }
  .main .block-container {
    padding-top: 2rem; padding-bottom: 2rem; padding-left: 3rem; padding-right: 3rem;
  }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ──────────────────────────────────────────────
# 2) 데이터 로드
# ──────────────────────────────────────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ──────────────────────────────────────────────
# 3) 헤더
# ──────────────────────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>📍 청주시 경유지 최적 경로</h1>", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 4) 메트릭
# ──────────────────────────────────────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2 = st.columns(2, gap="small")

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

# ──────────────────────────────────────────────
# 5) 레이아웃: 컨트롤 | 순서 | 지도
# ──────────────────────────────────────────────
col_ctrl, col_order, col_map = st.columns([1.5,1,4], gap="large")

# --- 컨트롤
with col_ctrl:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🚗 경로 설정")
    mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
    st.markdown("</div>", unsafe_allow_html=True)

    create_clicked = st.button("✅ 경로 생성", key="run")
    clear_clicked  = st.button("🚫 초기화", key="clear")
    st.markdown("""
      <script>
        const btns = document.querySelectorAll('.stButton>button');
        if(btns[0]) btns[0].classList.add('btn-create');
        if(btns[1]) btns[1].classList.add('btn-clear');
      </script>
    """, unsafe_allow_html=True)

# --- 방문 순서
with col_order:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🔢 방문 순서")
    if "order" in st.session_state:
        for i,name in enumerate(st.session_state.order,1):
            st.markdown(f"<p style='margin:4px 0;'><strong>{i}.</strong> {name}</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p style='color:#999;'>경로 생성 후 순서 표시됩니다.</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# --- 지도
with col_map:
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    G     = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    stops   = [start] + wps
    snapped = []
    for nm in stops:
        r = gdf[gdf["name"]==nm].iloc[0]
        pt = Point(r.lon, r.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    if clear_clicked:
        for k in ["segments","order","duration","distance"]:
            st.session_state.pop(k, None)

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
            r = requests.get(url, params=params); data=r.json() if r.status_code==200 else {}
            if data.get(key):
                leg = data[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]; tl += leg["distance"]
        if segs:
            st.session_state.order    = stops
            st.session_state.duration = td/60
            st.session_state.distance = tl/1000
            st.session_state.segments = segs

    st.markdown("<div class='card' style='padding:8px;'>", unsafe_allow_html=True)
    m = folium.Map(location=[clat,clon], tiles='CartoDB positron', zoom_start=12)

    folium.GeoJson(boundary, style_function=lambda f:{
        "color":"#26A69A","weight":2,"dashArray":"4,4","fillOpacity":0.05
    }).add_to(m)

    mc = MarkerCluster().add_to(m)
    for _, row in gdf.iterrows():
        folium.Marker([row.lat,row.lon], popup=row.name,
                      icon=folium.Icon(color="gray")).add_to(mc)

    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker([y,x],
            icon=folium.Icon(color="#008EAB",icon="flag"),
            tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)

    if "segments" in st.session_state:
        palette = ["#FF6B6B","#FFD93D","#6BCB77","#4D96FF","#E96479","#F9A826"]
        for i in range(len(st.session_state.segments),0,-1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine([(pt[1],pt[0]) for pt in seg],
                            color=palette[(i-1)%len(palette)], weight=6, opacity=0.9
            ).add_to(m)
            mid = seg[len(seg)//2]
            folium.map.Marker([mid[1],mid[0]],
                icon=DivIcon(html=f"<div style='background:{palette[(i-1)%len(palette)]};"
                                  "color:#fff;border-radius:50%;width:28px;height:28px;"
                                  "line-height:28px;text-align:center;font-weight:600;'>"
                                  f"{i}</div>")
            ).add_to(m)
        pts = [pt for seg in st.session_state.segments for pt in seg]
        m.fit_bounds([[min(p[1] for p in pts), min(p[0] for p in pts)],
                      [max(p[1] for p in pts), max(p[0] for p in pts)]])
    else:
        m.location=[clat,clon]; m.zoom_start=12

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=650)
    st.markdown("</div>", unsafe_allow_html=True)
