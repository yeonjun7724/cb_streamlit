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

# ────────────── Page & Token ──────────────
st.set_page_config(layout="wide")
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ────────────── Load Data ──────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ────────────── Sidebar: Order ──────────────
with st.sidebar:
    st.header("🔢 최적 방문 순서")
    if "order" in st.session_state:
        for i, name in enumerate(st.session_state.order, 1):
            st.write(f"{i}. {name}")
    else:
        st.write("경로를 생성해주세요")

# ────────────── Main Layout ──────────────
col_controls, col_map = st.columns([1, 3], gap="large")

with col_controls:
    st.markdown(
        """
        <div style="
            background:#ffffff;
            padding:16px;
            border-radius:8px;
            box-shadow:0 2px 4px rgba(0,0,0,0.1);
        ">
        <h3>🚗 경로 설정</h3>
        </div>
        """, unsafe_allow_html=True
    )
    mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps   = st.multiselect(
        "경유지 (최대 5개)", 
        [n for n in gdf["name"].dropna().unique() if n!=start]
    )

    st.markdown("")
    col_run, col_clear = st.columns(2)
    with col_run:
        run   = st.button("✅ 최적 경로")
    with col_clear:
        clear = st.button("🚫 초기화")

    st.markdown("---")
    st.markdown(
        """
        <div style="
            background:#ffffff;
            padding:16px;
            border-radius:8px;
            box-shadow:0 2px 4px rgba(0,0,0,0.1);
        ">
        <h3>📊 요약</h3>
        </div>
        """, unsafe_allow_html=True
    )
    dur  = st.session_state.get("duration", 0.0)
    dist = st.session_state.get("distance", 0.0)
    st.metric("⏱️ 예상 소요 시간", f"{dur:.1f} 분")
    st.metric("📏 예상 이동 거리", f"{dist:.2f} km")

with col_map:
    # compute center
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat):
        clat, clon = 36.64, 127.48

    # build graph
    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    G     = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    # snap stops
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

    if run and len(snapped) >= 2:
        segs = []; td=0; tl=0
        for i in range(len(snapped)-1):
            x1,y1 = snapped[i]; x2,y2 = snapped[i+1]
            coord = f"{x1},{y1};{x2},{y2}"
            if mode=="walking":
                url, key = (
                    f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}",
                    "routes"
                )
                params = {"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
            else:
                url, key = (
                    f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}",
                    "trips"
                )
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
                st.error("경로 생성 실패"); segs=[]
                break
        if segs:
            st.session_state.order    = stops
            st.session_state.duration = td/60
            st.session_state.distance = tl/1000
            st.session_state.segments = segs

    # draw folium
    m = folium.Map(location=[clat, clon], zoom_start=12)
    folium.GeoJson(
        boundary,
        style_function=lambda f: {
            "color":"#2A9D8F","weight":3,"dashArray":"5,5",
            "fillColor":"#2A9D8F","fillOpacity":0.1
        }
    ).add_to(m)

    # all points gray
    cluster = MarkerCluster().add_to(m)
    for _, r in gdf.iterrows():
        folium.Marker([r.lat,r.lon], popup=r.name,
                      icon=folium.Icon(color="gray")).add_to(cluster)

    # stops blue
    for idx,(x,y) in enumerate(snapped,1):
        folium.Marker(
            [y,x],
            icon=folium.Icon(color="blue"),
            tooltip=f"{idx}. {st.session_state.get('order',stops)[idx-1]}"
        ).add_to(m)

    # segments reversed order
    if "segments" in st.session_state:
        colors = ["#e6194b","#3cb44b","#ffe119","#4363d8","#f58231","#911eb4"]
        for i in range(len(st.session_state.segments), 0, -1):
            seg = st.session_state.segments[i-1]
            folium.PolyLine(
                [(pt[1],pt[0]) for pt in seg],
                color=colors[(i-1)%len(colors)],
                weight=6,opacity=0.8
            ).add_to(m)
            # nicer circular label
            mid = seg[len(seg)//2]
            html = f"""
            <div style="
                background:{colors[(i-1)%len(colors)]};
                color:white;
                border-radius:50%;
                width:26px;height:26px;
                line-height:26px;
                text-align:center;
                font-size:16px;
                font-weight:600;
                box-shadow:0 1px 3px rgba(0,0,0,0.5);
            ">{i}</div>
            """
            folium.map.Marker([mid[1],mid[0]], icon=DivIcon(html=html)).add_to(m)
        pts = [pt for seg in st.session_state.segments for pt in seg]
        lats = [p[1] for p in pts]; lons = [p[0] for p in pts]
        m.fit_bounds([[min(lats),min(lons)],[max(lats),max(lons)]])
    else:
        sx, sy = snapped[0]
        m.location = [sy, sx]; m.zoom_start = 15

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=700)
