import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests
from streamlit_folium import st_folium
import openai
import math
import os

# ──────────────────────────────
# ✅ 환경변수 불러오기
# ──────────────────────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q" 
openai.api_key = "sk-proj-CrnyAxHpjHnHg6wu4iuTFlMRW8yFgSaAsmk8rTKcAJrYkPocgucoojPeVZ-uARjei6wyEILHmgT3BlbkFJ2_tSjk8mGQswRVBPzltFNh7zXYrsTfOIT3mzESkqrz2vbUsCIw3O1a2I6txAACdi673MitM1UA4"

# ──────────────────────────────
# ✅ 데이터 로드
# ──────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()

# 카페 포맷 함수
def format_cafes(cafes_df):
    cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
    
    if len(cafes_df) == 0:
        return "주변에 등록된 카페 정보가 없습니다."
    
    elif len(cafes_df) == 1:
        row = cafes_df.iloc[0]
        if all(x not in row["c_review"] for x in ["없음", "없읍"]):
            return f"**{row['c_name']}** ({row['c_value']}⭐)\n{row['c_review']}"
        else:
            return f"**{row['c_name']}** ({row['c_value']}⭐)"
    
    else:
        result = []
        for (name, value), group in cafes_df.groupby(['c_name', 'c_value']):
            reviews = group['c_review'].dropna().unique()
            reviews = [r for r in reviews if all(x not in r for x in ["없음", "없읍"])]
            
            if reviews:
                result.append(f"**{name}** ({value}⭐)\n{reviews[0]}")
            else:
                result.append(f"**{name}** ({value}⭐)")
        
        return "\n\n".join(result[:3])

# ──────────────────────────────
# ✅ 세션 상태 초기화
# ──────────────────────────────
if 'order' not in st.session_state:
    st.session_state.order = []
if 'segments' not in st.session_state:
    st.session_state.segments = []
if 'duration' not in st.session_state:
    st.session_state.duration = 0.0
if 'distance' not in st.session_state:
    st.session_state.distance = 0.0
if 'auto_gpt_input' not in st.session_state:
    st.session_state.auto_gpt_input = ""

# ──────────────────────────────
# ✅ 페이지 설정 & 디자인
# ──────────────────────────────
st.set_page_config(
    page_title="청풍로드", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* 기본 스타일 리셋 */
    .main > div {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }
    
    /* 헤더 숨기기 */
    header[data-testid="stHeader"] {
        display: none;
    }
    
    /* 메인 컨테이너 */
    .stApp {
        background: #fafafa;
    }
    
    /* 타이틀 */
    .main-title {
        font-size: 2.2rem;
        font-weight: 300;
        color: #202124;
        text-align: center;
        margin: 0 0 0.5rem 0;
        letter-spacing: -0.5px;
    }
    
    .title-line {
        width: 60px;
        height: 2px;
        background: #4285f4;
        margin: 0 auto 2.5rem auto;
    }
    
    /* 섹션 제목 */
    .section-title {
        font-size: 1.1rem;
        font-weight: 500;
        color: #202124;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e8eaed;
    }
    
    /* 버튼 스타일 */
    .stButton > button {
        background: white;
        color: #3c4043;
        border: 1px solid #dadce0;
        border-radius: 6px;
        padding: 10px 20px;
        font-size: 0.9rem;
        font-weight: 500;
        width: 100%;
        height: 38px;
        transition: all 0.15s ease;
    }
    
    .stButton > button:hover {
        background: #f8f9fa;
        border-color: #bdc1c6;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    
    .stButton > button:focus {
        border-color: #4285f4;
        box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.2);
    }
    
    /* 메트릭 카드 */
    .metric-card {
        background: white;
        border: 1px solid #dadce0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        margin-bottom: 12px;
        min-height: 80px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    .metric-title {
        font-size: 0.85rem;
        color: #5f6368;
        margin-bottom: 4px;
        font-weight: 400;
    }
    
    .metric-value {
        font-size: 1.4rem;
        font-weight: 400;
        color: #202124;
        line-height: 1.2;
    }
    
    /* 방문 순서 */
    .order-card {
        background: white;
        border: 1px solid #dadce0;
        border-radius: 8px;
        padding: 16px;
        margin-top: 16px;
    }
    
    .order-item {
        padding: 6px 0;
        border-bottom: 1px solid #f1f3f4;
        font-size: 0.9rem;
        color: #3c4043;
    }
    
    .order-item:last-child {
        border-bottom: none;
    }
    
    .order-number {
        color: #5f6368;
        font-weight: 500;
        margin-right: 8px;
    }
    
    /* GPT 섹션 */
    .gpt-section {
        background: white;
        border: 1px solid #dadce0;
        border-radius: 8px;
        padding: 24px;
        margin-top: 24px;
    }
    
    .gpt-title {
        font-size: 1.1rem;
        font-weight: 500;
        color: #202124;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid #e8eaed;
    }
    
    /* 관광지 정보 카드 */
    .place-card {
        background: #f8f9fa;
        border-left: 3px solid #4285f4;
        padding: 16px;
        margin: 12px 0;
        border-radius: 0 6px 6px 0;
    }
    
    .place-title {
        font-size: 1rem;
        font-weight: 500;
        color: #202124;
        margin-bottom: 8px;
    }
    
    .place-content {
        font-size: 0.9rem;
        line-height: 1.5;
        color: #3c4043;
    }
    
    /* 폼 스타일 */
    .stTextInput > div > div > input {
        border: 1px solid #dadce0;
        border-radius: 6px;
        padding: 10px 12px;
        font-size: 0.9rem;
        height: 38px;
    }
    
    .stSelectbox > div > div > div {
        border: 1px solid #dadce0;
        border-radius: 6px;
        font-size: 0.9rem;
        min-height: 38px;
    }
    
    .stMultiSelect > div > div > div {
        border: 1px solid #dadce0;
        border-radius: 6px;
        font-size: 0.9rem;
        min-height: 38px;
    }
    
    /* 라디오 버튼 */
    .stRadio > div {
        flex-direction: row;
        gap: 20px;
    }
    
    .stRadio label {
        font-size: 0.9rem;
    }
    
    /* 컨트롤 섹션 간격 */
    .control-group {
        margin-bottom: 16px;
    }
    
    .control-group:last-child {
        margin-bottom: 0;
    }
    
    /* 라벨 스타일 */
    .stSelectbox label, 
    .stMultiSelect label, 
    .stRadio label {
        font-size: 0.9rem;
        color: #3c4043;
        font-weight: 500;
    }
    
    /* 여백 조정 */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
        max-width: 1400px;
    }
    
    /* 지도 스타일 */
    .leaflet-container {
        border-radius: 8px;
        border: 1px solid #dadce0;
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────
# ✅ 헤더
# ──────────────────────────────
st.markdown('''
<h1 class="main-title">청풍로드</h1>
<div class="title-line"></div>
''', unsafe_allow_html=True)

# ──────────────────────────────
# ✅ 메인 레이아웃
# ──────────────────────────────
col1, col2 = st.columns([1, 2.2], gap="large")

# 좌측: 컨트롤 패널
with col1:
    # 경로 설정
    st.markdown('<div class="section-title">경로 설정</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="control-group">', unsafe_allow_html=True)
    mode = st.radio("이동 수단", ["자동차", "도보"], horizontal=True, key="mode_key")
    st.markdown('</div>', unsafe_allow_html=True)
    
    mode_en = "driving" if mode == "자동차" else "walking"
    
    st.markdown('<div class="control-group">', unsafe_allow_html=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique(), key="start_key")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="control-group">', unsafe_allow_html=True)
    wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != st.session_state.get("start_key", "")], key="wps_key")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 버튼들
    col_btn1, col_btn2 = st.columns(2, gap="small")
    with col_btn1:
        create_clicked = st.button("경로 생성")
    with col_btn2:
        clear_clicked = st.button("초기화")
    
    # 메트릭
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">예상 소요 시간</div>
        <div class="metric-value">{st.session_state.get("duration", 0.0):.0f}분</div>
    </div>
    <div class="metric-card">
        <div class="metric-title">예상 이동 거리</div>
        <div class="metric-value">{st.session_state.get("distance", 0.0):.1f}km</div>
    </div>
    ''', unsafe_allow_html=True)
    
    # 방문 순서
    if st.session_state.get("order"):
        st.markdown('<div class="order-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title" style="margin-bottom: 12px; border: none; padding-bottom: 0;">방문 순서</div>', unsafe_allow_html=True)
        for i, name in enumerate(st.session_state["order"], 1):
            st.markdown(f'<div class="order-item"><span class="order-number">{i}.</span>{name}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# 우측: 지도
with col2:
    # 초기화 처리
    if clear_clicked:
        for k in ["segments", "order", "duration", "distance", "auto_gpt_input"]:
            st.session_state[k] = [] if k in ["segments", "order"] else 0.0
        for widget_key in ["mode_key", "start_key", "wps_key"]:
            st.session_state.pop(widget_key, None)
        st.rerun()
    
    # 지도 설정
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

    @st.cache_data
    def load_graph(lat, lon):
        try:
            return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
        except:
            return ox.graph_from_point((36.64, 127.48), dist=3000, network_type="all")
    
    G = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    stops = [start] + wps
    snapped = []
    
    # 스냅핑
    try:
        for nm in stops:
            r = gdf[gdf["name"] == nm].iloc[0]
            pt = Point(r.lon, r.lat)
            edges["d"] = edges.geometry.distance(pt)
            ln = edges.loc[edges["d"].idxmin()]
            sp = ln.geometry.interpolate(ln.geometry.project(pt))
            snapped.append((sp.x, sp.y))
    except Exception:
        for nm in stops:
            r = gdf[gdf["name"] == nm].iloc[0]
            snapped.append((r.lon, r.lat))

    # 경로 생성
    if create_clicked and len(snapped) >= 2:
        try:
            segs, td, tl = [], 0.0, 0.0
            for i in range(len(snapped) - 1):
                x1, y1 = snapped[i]
                x2, y2 = snapped[i + 1]
                coord = f"{x1},{y1};{x2},{y2}"
                
                if mode_en == "walking":
                    url = f"https://api.mapbox.com/directions/v5/mapbox/{mode_en}/{coord}"
                    params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}
                    key = "routes"
                else:
                    url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode_en}/{coord}"
                    params = {
                        "geometries": "geojson", "overview": "full",
                        "source": "first", "destination": "last", "roundtrip": "false",
                        "access_token": MAPBOX_TOKEN
                    }
                    key = "trips"
                
                r = requests.get(url, params=params)
                data_resp = r.json() if r.status_code == 200 else {}
                
                if data_resp.get(key):
                    leg = data_resp[key][0]
                    segs.append(leg["geometry"]["coordinates"])
                    td += leg.get("duration", 0)
                    tl += leg.get("distance", 0)
            
            if segs:
                st.session_state["order"] = stops
                st.session_state["duration"] = td / 60
                st.session_state["distance"] = tl / 1000
                st.session_state["segments"] = segs
        except Exception:
            st.error("경로 생성에 실패했습니다.")

    # 지도 렌더링
    m = folium.Map(location=[clat, clon], zoom_start=12, tiles="CartoDB Positron")
    
    # 경계
    folium.GeoJson(boundary, style_function=lambda f: {
        "color": "#9aa0a6", "weight": 1, "fillOpacity": 0.02
    }).add_to(m)
    
    # 마커 클러스터 추가 (필수!)
    mc = MarkerCluster().add_to(m)
    for _, row in gdf.iterrows():
        folium.Marker(
            [row.lat, row.lon], 
            popup=folium.Popup(row.name, max_width=200),
            tooltip=row.name,
            icon=folium.Icon(color="gray", icon="info-sign")
        ).add_to(mc)
    
    # 경로 지점 (마커 클러스터 위에 표시)
    current_order = st.session_state.get("order", stops)
    for idx, (x, y) in enumerate(snapped, 1):
        place_name = current_order[idx - 1] if idx <= len(current_order) else f"지점 {idx}"
        folium.Marker([y, x],
                      icon=folium.Icon(color="red", icon="flag"),
                      tooltip=f"{idx}. {place_name}",
                      popup=folium.Popup(f"<b>{idx}. {place_name}</b>", max_width=200)
        ).add_to(m)
    
    # 경로 라인
    if st.session_state.get("segments"):
        palette = ["#4285f4", "#34a853", "#ea4335", "#fbbc04"]
        segments = st.session_state["segments"]
        for i, seg in enumerate(segments):
            folium.PolyLine([(pt[1], pt[0]) for pt in seg],
                            color=palette[i % len(palette)], 
                            weight=4, 
                            opacity=0.8
            ).add_to(m)
        
        try:
            pts = [pt for seg in segments for pt in seg if seg]
            if pts:
                m.fit_bounds([[min(p[1] for p in pts), min(p[0] for p in pts)],
                              [max(p[1] for p in pts), max(p[0] for p in pts)]])
        except:
            pass
    
    st_folium(m, width="100%", height=580, returned_objects=[])

# ──────────────────────────────
# ✅ GPT 가이드
# ──────────────────────────────
st.markdown('<div class="gpt-section">', unsafe_allow_html=True)
st.markdown('<div class="gpt-title">관광지 정보</div>', unsafe_allow_html=True)

# OpenAI 클라이언트
client = openai.OpenAI(api_key="sk-proj-CrnyAxHpjHnHg6wu4iuTFlMRW8yFgSaAsmk8rTKcAJrYkPocgucoojPeVZ-uARjei6wyEILHmgT3BlbkFJ2_tSjk8mGQswRVBPzltFNh7zXYrsTfOIT3mzESkqrz2vbUsCIw3O1a2I6txAACdi673MitM1UA4")

if st.button("선택된 경로의 관광지 정보 보기", disabled=not st.session_state.get("order")):
    show_info = True
else:
    show_info = False

if show_info and st.session_state.get("order"):
    for place in st.session_state["order"][:3]:
        matched = data[data['t_name'].str.contains(place, na=False)]
        
        # GPT 소개
        try:
            gpt_intro = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "청주 관광지를 간단히 소개해주세요."},
                    {"role": "user", "content": f"{place}를 한 문단으로 설명해주세요."}
                ]
            ).choices[0].message.content
        except:
            gpt_intro = f"{place}에 대한 정보를 불러올 수 없습니다."
        
        # 카드 형태로 표시
        st.markdown(f'''
        <div class="place-card">
            <div class="place-title">{place}</div>
            <div class="place-content">{gpt_intro}</div>
        </div>
        ''', unsafe_allow_html=True)
        
        # 카페 정보
        if not matched.empty:
            cafes = matched[['c_name', 'c_value', 'c_review']].drop_duplicates()
            cafe_info = format_cafes(cafes)
            if cafe_info != "주변에 등록된 카페 정보가 없습니다.":
                st.markdown(f'<div class="place-content" style="margin-top:8px; padding-top:8px; border-top:1px solid #e8eaed;"><strong>주변 카페</strong><br>{cafe_info}</div>', unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
