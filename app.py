import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests
import math
from streamlit_folium import st_folium
import pandas as pd
from openai import OpenAI
from html import escape

# ──────────────────────────────────────────────
# 기본 페이지 세팅
# ──────────────────────────────────────────────
st.set_page_config(page_title="청주시 통합 관광 시스템", layout="wide")

# ──────────────────────────────────────────────
# 탭 생성
# ──────────────────────────────────────────────
tab1, tab2 = st.tabs(["📍 경로 최적화", "🏞️ 문화 관광가이드"])

# ──────────────────────────────────────────────
# 탭 1: 경로 최적화
# ──────────────────────────────────────────────
with tab1:
    try:
        gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
        boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

        gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y

        MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN"

        dur = st.session_state.get("tour_duration", 0.0)
        dist = st.session_state.get("tour_distance", 0.0)

        st.metric("예상 소요 시간(분)", f"{dur:.1f}")
        st.metric("예상 이동 거리(km)", f"{dist:.2f}")

        start = st.selectbox("출발지 선택", gdf["name"].dropna().unique())
        wps = st.multiselect("경유지 선택", [n for n in gdf["name"].dropna().unique() if n != start])
        mode = st.radio("이동 모드", ["driving", "walking"], horizontal=True)

        create_clicked = st.button("경로 생성")
        clear_clicked = st.button("초기화")

        ctr = boundary.geometry.centroid
        clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
        if pd.isna(clat) or pd.isna(clon):
            clat, clon = 36.64, 127.48

        @st.cache_data(allow_output_mutation=True)
        def load_graph(lat, lon):
            return ox.graph_from_point((lat, lon), dist=3000, network_type="all")

        G = load_graph(clat, clon)
        edges = ox.graph_to_gdfs(G, nodes=False)

        stops = [start] + wps
        snapped = []
        for nm in stops:
            r = gdf[gdf["name"] == nm].iloc[0]
            if pd.isna(r.lon) or pd.isna(r.lat):
                continue
            pt = Point(r.lon, r.lat)
            edges["d"] = edges.geometry.distance(pt)
            ln = edges.loc[edges["d"].idxmin()]
            sp = ln.geometry.interpolate(ln.geometry.project(pt))
            snapped.append((sp.x, sp.y))

        if clear_clicked:
            for k in ["tour_segments", "tour_order", "tour_duration", "tour_distance"]:
                st.session_state.pop(k, None)

        if create_clicked and len(snapped) >= 2:
            segs, td, tl = [], 0.0, 0.0
            for i in range(len(snapped) - 1):
                x1, y1 = snapped[i]
                x2, y2 = snapped[i + 1]
                coord = f"{x1},{y1};{x2},{y2}"
                if mode == "walking":
                    url = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}"
                    key = "routes"
                    params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}
                else:
                    url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}"
                    key = "trips"
                    params = {
                        "geometries": "geojson",
                        "overview": "full",
                        "source": "first",
                        "destination": "last",
                        "roundtrip": "false",
                        "access_token": MAPBOX_TOKEN,
                    }
                try:
                    r = requests.get(url, params=params)
                    data = r.json() if r.status_code == 200 else {}
                except Exception as e:
                    st.warning(f"요청 오류: {e}")
                    data = {}

                if data.get(key):
                    leg = data[key][0]
                    segs.append(leg["geometry"]["coordinates"])
                    td += leg["duration"]
                    tl += leg["distance"]

            if segs:
                st.session_state.tour_order = stops
                st.session_state.tour_duration = td / 60
                st.session_state.tour_distance = tl / 1000
                st.session_state.tour_segments = segs

        m = folium.Map(location=[clat, clon], tiles='CartoDB positron', zoom_start=12)
        folium.GeoJson(boundary).add_to(m)

        mc = MarkerCluster().add_to(m)
        for _, row in gdf.iterrows():
            folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)

        if "tour_segments" in st.session_state:
            palette = ["#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF"]
            for i, seg in enumerate(reversed(st.session_state.tour_segments), 1):
                folium.PolyLine([(pt[1], pt[0]) for pt in seg], color=palette[(i - 1) % len(palette)], weight=6).add_to(m)
                mid = seg[len(seg) // 2]
                safe_html = escape(str(i))
                folium.map.Marker(
                    [mid[1], mid[0]],
                    icon=DivIcon(html=f"<div style='background:{palette[(i-1)%len(palette)]};"
                                      "color:#fff;border-radius:50%;width:28px;height:28px;"
                                      "line-height:28px;text-align:center;font-weight:600;'>"
                                      f"{safe_html}</div>")
                ).add_to(m)

        st_folium(m, width="100%", height=600)

    except Exception as e:
        st.error(f"에러 발생: {e}")

# ──────────────────────────────────────────────
# 탭 2: 문화 관광가이드
# ──────────────────────────────────────────────
with tab2:
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ OpenAI API 키가 없습니다.")
        st.stop()
    client = OpenAI(api_key=api_key)

    try:
        data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()
    except:
        st.error("cj_data_final.csv 파일이 없습니다.")
        st.stop()

    def format_cafes(cafes_df):
        cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
        if len(cafes_df) == 0:
            return "☕ 현재 주변에 등록된 카페 정보가 없어요."
        elif len(cafes_df) == 1:
            row = cafes_df.iloc[0]
            if all(x not in row["c_review"] for x in ["없음", "없읍"]):
                return f"""☕ **주변 추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})  
{row['c_review']}"""
            else:
                return f"""☕ **주변 추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})"""
        else:
            result = ["☕ **주변 추천 카페**"]
            for _, row in cafes_df.iterrows():
                result.append(f"- **{row['c_name']}** (⭐ {row['c_value']})")
            return "\n".join(result)

    st.write("✅ format_cafes 함수 오류 없이 준비 완료!")

3333331
