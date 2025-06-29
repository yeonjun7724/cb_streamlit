# app.py

import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests, math
from streamlit_folium import st_folium
from openai import OpenAI

# ──────────────────────────────
# 1) 페이지 & CSS
# ──────────────────────────────
st.set_page_config(page_title="청주시 경유지 최적 경로", layout="wide")
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; background: #F9F9F9; color: #333; }
  h1 { font-weight:600; }
  .card { background:#FFF; border-radius:12px; padding:20px; box-shadow:0 2px 6px rgba(0,0,0,0.1); margin-bottom:24px; }
  .stButton>button { border-radius:8px; font-weight:600; padding:10px 24px; }
  .btn-create { background: linear-gradient(90deg,#00C9A7,#008EAB); color:#FFF; }
  .btn-clear  { background:#E63946; color:#FFF; }
  .leaflet-container { border-radius:12px !important; box-shadow:0 2px 6px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN   = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"
OPENAI_API_KEY = "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"
client = OpenAI(api_key=OPENAI_API_KEY)

# ──────────────────────────────
# 2) 데이터 로드
# ──────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ──────────────────────────────
# 3) session_state 초기화
# ──────────────────────────────
if "order" not in st.session_state:
    st.session_state["order"] = []
if "segments" not in st.session_state:
    st.session_state["segments"] = []
if "duration" not in st.session_state:
    st.session_state["duration"] = 0.0
if "distance" not in st.session_state:
    st.session_state["distance"] = 0.0
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = [{"role": "system", "content": "당신은 청주시 문화관광 전문 가이드입니다."}]

# ──────────────────────────────
# 4) 헤더
# ──────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>📍 청주시 경유지 최적 경로 & GPT</h1>", unsafe_allow_html=True)

# ──────────────────────────────
# 5) 레이아웃: 좌(경유지) | 우(GPT)
# ──────────────────────────────
col_left, col_right = st.columns([3, 1.5], gap="large")

with col_left:
    dur  = st.session_state["duration"]
    dist = st.session_state["distance"]
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

    col_ctrl, col_order, col_map = st.columns([1.5,1,4], gap="large")

    with col_ctrl:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("🚗 경로 설정")
        mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
        start = st.selectbox("출발지", gdf["name"].dropna().unique())
        wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
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

    with col_order:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("🔢 방문 순서")
        if st.session_state["order"]:
            for i, name in enumerate(st.session_state["order"], 1):
                st.markdown(f"<p style='margin:4px 0;'><strong>{i}.</strong> {name}</p>", unsafe_allow_html=True)
        else:
            st.markdown("<p style='color:#999;'>경로 생성 후 순서 표시됩니다.</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

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

        if create_clicked and len(snapped) >= 2:
            segs, td, tl = [], 0.0, 0.0
            for i in range(len(snapped)-1):
                x1,y1 = snapped[i]; x2,y2 = snapped[i+1]
                coord = f"{x1},{y1};{x2},{y2}"
                if mode == "walking":
                    url,key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}","routes"
                    params={"geometries":"geojson","overview":"full","access_token":MAPBOX_TOKEN}
                else:
                    url,key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}","trips"
                    params={
                      "geometries":"geojson","overview":"full",
                      "source":"first","destination":"last","roundtrip":"false",
                      "access_token":MAPBOX_TOKEN
                    }
                r = requests.get(url, params=params)
                data = r.json() if r.status_code == 200 else {}
                if key in data:
                    leg = data[key][0]
                    segs.append(leg["geometry"]["coordinates"])
                    td += leg["duration"]; tl += leg["distance"]
            if segs:
                st.session_state["order"]    = stops
                st.session_state["duration"] = td / 60
                st.session_state["distance"] = tl / 1000
                st.session_state["segments"] = segs
            else:
                st.warning("🚫 경로를 가져올 수 없습니다. 출발지/경유지를 다시 확인하세요!")

        st.markdown("<div class='card' style='padding:8px;'>", unsafe_allow_html=True)
        m = folium.Map(location=[clat, clon], zoom_start=12)
        folium.GeoJson(boundary).add_to(m)
        mc = MarkerCluster().add_to(m)
        for _, row in gdf.iterrows():
            folium.Marker([row.lat,row.lon], popup=row.name).add_to(mc)

        for idx, ((x,y), name) in enumerate(zip(snapped, st.session_state.get("order", stops)), 1):
            folium.Marker([y,x],
                tooltip=f"{idx}. {name}",
                icon=folium.Icon(color="#008EAB", icon="flag")
            ).add_to(m)

        if st.session_state["segments"]:
            palette = ["#FF5252","#FFEA00","#69F0AE","#40C4FF","#E040FB","#FF8F00"]
            for i, seg in enumerate(st.session_state["segments"], 1):
                folium.PolyLine([(pt[1], pt[0]) for pt in seg],
                    color=palette[(i-1)%len(palette)], weight=6, opacity=0.9).add_to(m)
                mid = seg[len(seg)//2]
                folium.map.Marker([mid[1],mid[0]],
                    icon=DivIcon(html=f"<div style='background:{palette[(i-1)%len(palette)]};"
                        "color:#fff;border-radius:50%;width:28px;height:28px;"
                        "line-height:28px;text-align:center;font-weight:600;'>"
                        f"{i}</div>")
                ).add_to(m)

        folium.LayerControl().add_to(m)
        st_folium(m, width="100%", height=650)
        st.markdown("</div>", unsafe_allow_html=True)

with col_right:
    st.subheader("🏛️ 청주 관광 GPT 가이드")
    for msg in st.session_state["chat_messages"][1:]:
        align = "right" if msg["role"]=="user" else "left"
        bg = "#dcf8c6" if msg["role"]=="user" else "#fff"
        st.markdown(
            f"<div style='text-align:{align};background:{bg};padding:8px;border-radius:10px;margin-bottom:6px'>{msg['content']}</div>",
            unsafe_allow_html=True)

    st.divider()
    with st.form("chat_form"):
        user_input = st.text_input("📍 관광지명을 입력하세요")
        submitted  = st.form_submit_button("보내기")

    if submitted and user_input:
        st.session_state["chat_messages"].append({"role":"user","content":user_input})
        with st.spinner("GPT 답변 생성 중..."):
            gpt_reply = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=st.session_state["chat_messages"]
            ).choices[0].message.content
            st.session_state["chat_messages"].append({"role":"assistant","content":gpt_reply})
