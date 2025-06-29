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
# 1. Page & CSS Config
# ───────────────────────────────────────────────────────────
st.set_page_config(page_title="청주시 경유지 최적 경로", layout="wide")
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
  html, body, [class*="css"] { font-family: 'Roboto', sans-serif; background: #121212; color: #E0E0E0; }
  h1, h2, h3, h4, h5 { color: #FFFFFF; margin: 0; }
  .card {
      background: #1E1E1E;
      border-radius: 12px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.6);
      padding: 20px;
      margin-bottom: 24px;
  }
  .stButton > button {
      font-weight: 500;
      border-radius: 8px;
      padding: 10px 20px;
      transition: background 0.2s, transform 0.1s;
  }
  .stButton > button:hover { opacity: 0.9; transform: translateY(-1px); }
  .stButton > button:active { transform: translateY(1px); }
  .primary { background-color: #2962FF; color: #fff !important; }
  .secondary { background-color: #D32F2F; color: #fff !important; }
  .leaflet-container { border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.6); }
  .stSelectbox>label, .stMultiselect>label, .stRadio>label { color: #B0BEC5 !important; }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ───────────────────────────────────────────────────────────
# 2. Data Load
# ───────────────────────────────────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ───────────────────────────────────────────────────────────
# 3. Header
# ───────────────────────────────────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>📍 청주시 경유지 최적 경로</h1>", unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────
# 4. Top Metrics
# ───────────────────────────────────────────────────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
c1, c2, c3 = st.columns([1,1,4], gap="small")

with c1:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4>⏱️ 예상 소요 시간</h4>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='margin-top:8px;'>{dur:.1f} 분</h2>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with c2:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4>📏 예상 이동 거리</h4>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='margin-top:8px;'>{dist:.2f} km</h2>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ───────────────────────────────────────────────────────────
# 5. Main: Controls & Map
# ───────────────────────────────────────────────────────────
ctrl, mp = st.columns([1.5, 4], gap="large")

with ctrl:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h3>🚗 경로 설정</h3>", unsafe_allow_html=True)
    mode  = st.radio("", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
    st.write("")  # spacer
    run   = st.button("✅ 경로 생성", key="run", help="최적 경로 계산", args=None, kwargs=None)
    clear = st.button("🚫 초기화", key="clear", help="초기화")
    st.markdown("</div>", unsafe_allow_html=True)

with mp:
    # compute center
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

    # OSMnx graph cache
    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    G     = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    # snap points
    stops = [start] + wps
    snapped = []
    for name in stops:
        r = gdf[gdf["name"]==name].iloc[0]
        pt = Point(r.lon, r.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    if clear:
        for k in ["segments","order","duration","distance"]:
            st.session_state.pop(k, None)

    # call Mapbox API per leg
    if run and len(snapped)>=2:
        segs, td, tl = [],0.0,0.0
        for i in range(len(snapped)-1):
            x1,y1 = snapped[i]; x2,y2 = snapped[i+1]
            coord = f"{x1},{y1};{x2},{y2}"
            if mode=="walking":
                url,key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}","routes"
                params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            else:
                url,key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}","trips"
                params = {
                    "geometries":"geojson","overview":"full",
                    "source":"first","destination":"last","roundtrip":"false",
                    "access_token":MAPBOX_TOKEN
                }
            res = requests.get(url, params=params); data = res.json() if res.status_code==200 else {}
            if data.get(key):
                leg = data[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]; tl += leg["distance"]
        if segs:
            st.session_state.order    = stops
            st.session_state.duration = td/60
            st.session_state.distance = tl/1000
            st.session_state.segments = segs

    # render map
    st.markdown("<div class='card' style='padding:8px;'>", unsafe_allow_html=True)
    m = folium.Map(location=[clat, clon], zoom_start=12)
    folium.GeoJson(boundary, style_function=lambda f:{
        "color":"#26A69A","weight":2,"dashArray":"5,5","fillOpacity":0.1
    }).add_to(m)

    # all points
    mc = MarkerCluster().add_to(m)
    for _,row in gdf.iterrows():
        folium.Marker([row.lat,row.lon], popup=row.name,
                      icon=folium.Icon(color="gray",icon="info-sign")).add_to(mc)

    # stops
    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker([y,x],
            icon=folium.Icon(color="blue",icon="flag"),
            tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)

    # draw segments reversed
    if "segments" in st.session_state:
        cols = ["#FF5252","#FFEA00","#69F0AE","#40C4FF","#E040FB","#FF8F00"]
        for i in range(len(st.session_state.segments),0,-1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine(
                [(pt[1],pt[0]) for pt in seg],
                color=cols[(i-1)%len(cols)], weight=6, opacity=0.9
            ).add_to(m)
            mid = seg[len(seg)//2]
            folium.map.Marker([mid[1],mid[0]],
                icon=DivIcon(html=f"""<div style="
                    background:{cols[(i-1)%len(cols)]};
                    color:#fff;border-radius:50%;
                    width:30px;height:30px;line-height:30px;
                    text-align:center;font-size:16px;font-weight:600;
                    box-shadow:0 2px 4px rgba(0,0,0,0.4);
                ">{i}</div>""")
            ).add_to(m)
        # fit bounds
        allpts = [pt for seg in st.session_state.segments for pt in seg]
        lats = [p[1] for p in allpts]; lons = [p[0] for p in allpts]
        m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
    else:
        sx,sy = snapped[0]
        m.location=[sy,sx]; m.zoom_start=15

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=650)
    st.markdown("</div>", unsafe_allow_html=True)
