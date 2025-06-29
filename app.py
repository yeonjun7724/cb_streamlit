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
import json

# ──────────────────────────────
# 1) 기본 설정
# ──────────────────────────────
st.set_page_config(page_title="청주시 경유지 최적 경로 & GPT", layout="wide")

# ✅ Mapbox 토큰
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ✅ OpenAI 프로젝트 키 + 조직 ID
OPENAI_API_KEY = "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"
ORG_ID = "org-xxxxx"  # ← ⚠️ 반드시 본인 OpenAI 조직 ID로 바꾸세요!

# ──────────────────────────────
# 2) 데이터 로드
# ──────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ──────────────────────────────
# 3) session_state
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
if "auto_gpt_input" not in st.session_state:
    st.session_state["auto_gpt_input"] = ""

# ──────────────────────────────
# 4) 헤더
# ──────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>📍 청주시 경유지 최적 경로 & GPT</h1>", unsafe_allow_html=True)

# ──────────────────────────────
# 5) 레이아웃
# ──────────────────────────────
col_left, col_right = st.columns([3, 1.5], gap="large")

# ──────────────── 좌측: 경로 짜기 ────────────────
with col_left:
    dur, dist = st.session_state["duration"], st.session_state["distance"]
    st.metric("⏱️ 예상 소요 시간", f"{dur:.1f}분")
    st.metric("📏 예상 이동 거리", f"{dist:.2f}km")

    col_ctrl, col_order, col_map = st.columns([1.5, 1, 4], gap="large")

    with col_ctrl:
        mode  = st.radio("이동 모드", ["driving","walking"], horizontal=True)
        start = st.selectbox("출발지", gdf["name"].dropna().unique())
        wps   = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])

        create_clicked = st.button("✅ 경로 생성")
        clear_clicked  = st.button("🚫 초기화")

    with col_order:
        st.write("🔢 방문 순서")
        if st.session_state["order"]:
            for i, name in enumerate(st.session_state["order"], 1):
                st.write(f"{i}. {name}")
        else:
            st.write("경로 생성 후 표시됩니다.")

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
                st.warning("🚫 경로를 가져올 수 없습니다!")

        m = folium.Map(location=[clat, clon], zoom_start=12)
        folium.GeoJson(boundary).add_to(m)
        mc = MarkerCluster().add_to(m)
        for _, row in gdf.iterrows():
            folium.Marker([row.lat,row.lon], popup=row.name).add_to(mc)

        for idx, ((x,y), name) in enumerate(zip(snapped, st.session_state.get("order", stops)), 1):
            folium.Marker([y,x], tooltip=f"{idx}. {name}",
                          icon=folium.Icon(color="#008EAB", icon="flag")).add_to(m)

        if st.session_state["segments"]:
            for seg in st.session_state["segments"]:
                folium.PolyLine([(pt[1], pt[0]) for pt in seg], color="red").add_to(m)

        st_folium(m, width="100%", height=600)

# ──────────────── 우측: GPT ────────────────
with col_right:
    st.write("🏛️ 청주 관광 GPT 가이드")
    for msg in st.session_state["chat_messages"][1:]:
        align = "right" if msg["role"]=="user" else "left"
        bg = "#dcf8c6" if msg["role"]=="user" else "#fff"
        st.markdown(
            f"<div style='text-align:{align};background:{bg};padding:8px;border-radius:10px;margin-bottom:6px'>{msg['content']}</div>",
            unsafe_allow_html=True)

    if st.button("🔁 방문 순서를 입력창에 불러오기"):
        route = st.session_state.get("order", [])
        if route:
            st.session_state["auto_gpt_input"] = ", ".join(route)
        else:
            st.warning("경로를 먼저 생성하세요!")

    with st.form("chat_form"):
        user_input = st.text_input(
            "📍 관광지명을 입력하세요",
            value=st.session_state.get("auto_gpt_input", ""),
            key="auto_gpt_input"
        )
        submitted  = st.form_submit_button("보내기")

    if submitted and user_input:
        st.session_state["chat_messages"].append({"role":"user","content":user_input})
        with st.spinner("GPT 답변 생성 중..."):
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Organization": ORG_ID
            }
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": st.session_state["chat_messages"]
            }
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                gpt_reply = response.json()["choices"][0]["message"]["content"]
                st.session_state["chat_messages"].append({"role":"assistant","content":gpt_reply})
            else:
                st.error(f"OpenAI API Error: {response.text}")
