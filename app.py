import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
from streamlit_folium import st_folium
import streamlit as st
import requests, math

# ────────────── Page Config ──────────────
st.set_page_config(layout="wide", page_title="청주시 경유지 최적 경로")

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ────────────── Load Data ──────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── Header ──────────────
st.markdown(
    """
    <h1 style="text-align:center; margin-bottom:10px;">📍 청주시 경유지 최적 경로 대시보드</h1>
    """, unsafe_allow_html=True
)

# ────────────── Full-width Metrics ──────────────
dur  = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)
m1, m2, m3 = st.columns([1,1,4], gap="small")
m1.markdown(f"""
  <div style="
    background:#f1c40f; padding:12px; border-radius:8px;
    color:#fff; font-weight:bold; text-align:center;
  ">
    ⏱️ 예상 소요 시간<br><span style="font-size:24px;">{dur:.1f} 분</span>
  </div>
""", unsafe_allow_html=True)
m2.markdown(f"""
  <div style="
    background:#2ecc71; padding:12px; border-radius:8px;
    color:#fff; font-weight:bold; text-align:center;
  ">
    📏 예상 이동 거리<br><span style="font-size:24px;">{dist:.2f} km</span>
  </div>
""", unsafe_allow_html=True)
m3.write("")  # spacer for symmetry

# ────────────── Main Row: Controls(1.5) + Map(3.5) ──────────────
ctrl_col, map_col = st.columns([1.5, 3.5], gap="large")

with ctrl_col:
    st.markdown(
        """
        <div style="
          background:rgba(255,255,255,0.9);
          padding:20px; border-radius:12px;
          box-shadow:0 4px 12px rgba(0,0,0,0.05);
          margin-bottom:20px;
        ">
          <h3 style="margin-bottom:12px;">🚗 경로 설정</h3>
        </div>
        """, unsafe_allow_html=True
    )
    mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect(
        "경유지", [n for n in gdf["name"].dropna().unique() if n!=start]
    )
    st.markdown("")  # spacer
    run   = st.button("✅ 경로 생성", use_container_width=True)
    clear = st.button("🚫 초기화",  use_container_width=True)

with map_col:
    # — Snap & API 호출 (이전과 동일)
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
    for name in stops:
        row = gdf[gdf["name"]==name].iloc[0]
        pt  = Point(row.lon, row.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    if clear:
        for k in ["segments","order","duration","distance"]:
            st.session_state.pop(k, None)

    if run and len(snapped)>=2:
        segs, td, tl = [],0.0,0.0
        for i in range(len(snapped)-1):
            p1, p2 = snapped[i], snapped[i+1]
            coord = f"{p1[0]},{p1[1]};{p2[0]},{p2[1]}"
            if mode=="walking":
                url,key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}", "routes"
                params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            else:
                url,key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}", "trips"
                params = {
                  "geometries":"geojson","overview":"full",
                  "source":"first","destination":"last","roundtrip":"false",
                  "access_token":MAPBOX_TOKEN
                }
            r = requests.get(url, params=params); j=r.json()
            if r.status_code==200 and j.get(key):
                leg = j[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]; tl += leg["distance"]
            else:
                st.error("경로 생성 실패")
                segs=[]; break
        if segs:
            st.session_state.order    = stops
            st.session_state.duration = td/60
            st.session_state.distance = tl/1000
            st.session_state.segments = segs

    # — Folium Map Container
    st.markdown(
        """
        <div style="
          background:#fff; border-radius:12px;
          box-shadow:0 4px 12px rgba(0,0,0,0.05);
          padding:8px;
        ">
        """, unsafe_allow_html=True
    )
    m = folium.Map(location=[clat,clon], zoom_start=12)
    folium.GeoJson(
        boundary,
        style_function=lambda f: {
            "color":"#2A9D8F","weight":2,"dashArray":"5,5",
            "fillOpacity":0.1
        }
    ).add_to(m)
    mc = MarkerCluster().add_to(m)
    for _, r in gdf.iterrows():
        folium.Marker([r.lat,r.lon], popup=r.name,
                      icon=folium.Icon(color="gray")).add_to(mc)
    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker([y,x],
                      icon=folium.Icon(color="blue", icon="info-sign"),
                      tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)
    if "segments" in st.session_state:
        cols = ["#e6194b","#3cb44b","#ffe119","#4363d8","#f58231","#911eb4"]
        for i in range(len(st.session_state.segments),0,-1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine([(pt[1],pt[0]) for pt in seg],
                            color=cols[(i-1)%len(cols)], weight=6, opacity=0.8
            ).add_to(m)
            mid = seg[len(seg)//2]
            html = f"""
            <div style="
              background:{cols[(i-1)%len(cols)]};
              color:#fff; border-radius:50%;
              width:28px;height:28px;line-height:28px;
              text-align:center;font-size:16px;
              font-weight:600;box-shadow:0 2px 6px rgba(0,0,0,0.3);
            ">{i}</div>
            """
            folium.map.Marker([mid[1],mid[0]],
                              icon=DivIcon(html=html)
            ).add_to(m)
        pts=[pt for seg in st.session_state.segments for pt in seg]
        lats=[p[1] for p in pts]; lons=[p[0] for p in pts]
        m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
    else:
        sx,sy=snapped[0]
        m.location=[sy,sx]; m.zoom_start=15

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=620)
    st.markdown("</div>", unsafe_allow_html=True)
