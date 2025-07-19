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
# ✅ 환경변수 불러오기 (Streamlit Cloud 호환에 저장된 키 사용)
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

# csv 파일에 카페 있을때 출력 / 카페 포맷 함수
def format_cafes(cafes_df):
    cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
    result = []

    if len(cafes_df) == 0:
        return ("현재 이 관광지 주변에 등록된 카페 정보는 없어요.  \n"
                "하지만 근처에 숨겨진 보석 같은 공간이 있을 수 있으니,  \n"
                "지도를 활용해 천천히 걸어보시는 것도 추천드립니다 😊")

    elif len(cafes_df) == 1:
        row = cafes_df.iloc[0]
        if all(x not in row["c_review"] for x in ["없음", "없읍"]):
            return f"☕ **주변 추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})  \n\"{row['c_review']}\""
        else:
            return f"☕ **주변 추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})"

    else:
        grouped = cafes_df.groupby(['c_name', 'c_value'])
        result.append("**주변의 평점 높은 카페들은 여기 있어요!** 🌼\n")
        for (name, value), group in grouped:
            reviews = group['c_review'].dropna().unique()
            reviews = [r for r in reviews if all(x not in r for x in ["없음", "없읍"])]
            top_reviews = reviews[:3]

            if top_reviews:
                review_text = "\n".join([f"\"{r}\"" for r in top_reviews])
                result.append(f"- **{name}** (⭐ {value})  \n{review_text}")
            else:
                result.append(f"- **{name}** (⭐ {value})")

        return "\n\n".join(result)

# ──────────────────────────────
# ✅ Session 초기화
# ──────────────────────────────
DEFAULTS = {
    "order": [],
    "segments": [],
    "duration": 0.0,
    "distance": 0.0,
    "messages": [{"role": "system", "content": "당신은 청주 문화관광 전문 가이드입니다."}],
    "auto_gpt_input": ""
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────
# ✅ 페이지 설정 & 깔끔한 디자인
# ──────────────────────────────
st.set_page_config(
    page_title="청풍로드", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* 기본 스타일 */
    .main > div {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }
    
    header[data-testid="stHeader"] {
        display: none;
    }
    
    .stApp {
        background: #fafafa;
    }
    
    /* 타이틀 스타일 */
    .main-title {
        font-size: 2.5rem;
        font-weight: 300;
        color: #202124;
        text-align: center;
        margin: 0 0 0.8rem 0;
        letter-spacing: -0.5px;
    }
    
    .title-underline {
        width: 80px;
        height: 3px;
        background: linear-gradient(90deg, #4285f4, #34a853);
        margin: 0 auto 2rem auto;
        border-radius: 2px;
    }
    
    /* 카드 스타일 */
    .control-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .metric-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .order-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .map-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    /* 섹션 제목 */
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #202124;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    /* 버튼 스타일 */
    .stButton > button {
        background: white;
        color: #3c4043;
        border: 1px solid #dadce0;
        border-radius: 8px;
        padding: 12px 20px;
        font-size: 14px;
        font-weight: 500;
        width: 100%;
        height: 44px;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        background: #f8f9fa;
        border-color: #4285f4;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* 주요 버튼 */
    .primary-button {
        background: #4285f4 !important;
        color: white !important;
        border-color: #4285f4 !important;
    }
    
    .secondary-button {
        background: #ea4335 !important;
        color: white !important;
        border-color: #ea4335 !important;
    }
    
    /* 메트릭 */
    .metric-title {
        font-size: 14px;
        color: #5f6368;
        margin-bottom: 8px;
        font-weight: 400;
    }
    
    .metric-value {
        font-size: 28px;
        font-weight: 400;
        color: #202124;
        line-height: 1.2;
    }
    
    /* 방문 순서 */
    .order-item {
        padding: 10px 0;
        border-bottom: 1px solid #f1f3f4;
        font-size: 15px;
        color: #3c4043;
        display: flex;
        align-items: center;
    }
    
    .order-item:last-child {
        border-bottom: none;
    }
    
    .order-number {
        background: #4285f4;
        color: white;
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        font-weight: 600;
        margin-right: 12px;
        flex-shrink: 0;
    }
    
    /* GPT 섹션 */
    .gpt-section {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 24px;
        margin-top: 32px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .place-info {
        background: #f8f9fa;
        border-left: 4px solid #4285f4;
        padding: 20px;
        margin: 16px 0;
        border-radius: 0 8px 8px 0;
    }
    
    .place-title {
        font-size: 18px;
        font-weight: 600;
        color: #202124;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .place-content {
        font-size: 14px;
        line-height: 1.6;
        color: #3c4043;
        margin-bottom: 12px;
    }
    
    .cafe-section {
        background: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 16px;
        margin-top: 12px;
        border-radius: 0 6px 6px 0;
    }
    
    /* 폼 스타일 */
    .stSelectbox label, .stMultiSelect label, .stRadio label {
        font-size: 14px;
        color: #3c4043;
        font-weight: 500;
        margin-bottom: 4px;
    }
    
    .stRadio > div {
        flex-direction: row;
        gap: 24px;
        margin-top: 8px;
    }
    
    /* 지도 스타일 */
    .leaflet-container {
        border-radius: 8px !important;
    }
    
    /* 간격 조정 */
    .block-container {
        padding-top: 1.5rem;
        max-width: 1400px;
    }
    
    /* 성공/경고 메시지 */
    .stSuccess, .stWarning, .stError {
        border-radius: 8px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────
# ✅ 헤더
# ──────────────────────────────
st.markdown('''
<div class="main-title">📍 청풍로드</div>
<div class="title-underline"></div>
''', unsafe_allow_html=True)

# ──────────────────────────────
# ✅ 메인 레이아웃 (4컬럼 유지)
# ──────────────────────────────
col1, col2, col3, col4 = st.columns([1.5, 1, 1, 3], gap="large")

# ------------------------------
# ✅ [좌] 경로 설정
# ------------------------------
with col1:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🚗 경로 설정</div>', unsafe_allow_html=True)

    mode = st.radio("이동 모드", ["driving", "walking"], horizontal=True, key="mode_key")
    start = st.selectbox("출발지", gdf["name"].dropna().unique(), key="start_key")
    wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != st.session_state.get("start_key", "")], key="wps_key")

    col_btn1, col_btn2 = st.columns(2, gap="small")
    with col_btn1:
        create_clicked = st.button("✅ 경로 생성")
    with col_btn2:
        clear_clicked = st.button("🚫 초기화")

    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------
# ✅ 초기화 처리
# ------------------------------
if clear_clicked:
    for k in ["segments", "order", "duration", "distance", "auto_gpt_input"]:
        st.session_state[k] = DEFAULTS.get(k, [] if k in ["segments", "order"] else 0.0)
    for widget_key in ["mode_key", "start_key", "wps_key"]:
        st.session_state.pop(widget_key, None)
    st.rerun()

# ------------------------------
# ✅ [중간] 방문 순서
# ------------------------------
with col2:
    st.markdown('<div class="order-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🔢 방문 순서</div>', unsafe_allow_html=True)
    
    current_order = st.session_state.get("order", [])
    if current_order:
        for i, name in enumerate(current_order, 1):
            st.markdown(f'''
            <div class="order-item">
                <div class="order-number">{i}</div>
                <div>{name}</div>
            </div>
            ''', unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#9aa0a6; text-align:center; padding:20px;">경로 생성 후 표시됩니다</div>', unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------
# ✅ [중간] KPI 카드
# ------------------------------
with col3:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">⏱️ 예상 소요 시간</div>
        <div class="metric-value">{st.session_state.get("duration", 0.0):.1f}분</div>
    </div>
    <div class="metric-card">
        <div class="metric-title">📏 예상 이동 거리</div>
        <div class="metric-value">{st.session_state.get("distance", 0.0):.2f}km</div>
    </div>
    ''', unsafe_allow_html=True)

# ------------------------------
# ✅ [우] 지도 (모든 기능 보존)
# ------------------------------
with col4:
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
    except Exception as e:
        st.error(f"지점 스냅핑 중 오류: {str(e)}")
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
                
                if mode == "walking":
                    url, key = f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coord}", "routes"
                    params = {"geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN}
                else:
                    url, key = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord}", "trips"
                    params = {
                        "geometries": "geojson", "overview": "full",
                        "source": "first", "destination": "last", "roundtrip": "false",
                        "access_token": MAPBOX_TOKEN
                    }
                
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
                st.success("✅ 경로가 성공적으로 생성되었습니다!")
            else:
                st.warning("⚠️ 경로 생성에 실패했습니다.")
        except Exception as e:
            st.error(f"경로 생성 중 오류: {str(e)}")

    # 지도 렌더링 (모든 기능 보존)
    st.markdown('<div class="map-card">', unsafe_allow_html=True)
    m = folium.Map(location=[clat, clon], zoom_start=12, tiles="CartoDB Positron")
    
    # 경계
    folium.GeoJson(boundary, style_function=lambda f: {
        "color": "#9aa0a6", "weight": 2, "dashArray": "4,4", "fillOpacity": 0.05
    }).add_to(m)
    
    # 마커 클러스터 (필수!)
    mc = MarkerCluster().add_to(m)
    for _, row in gdf.iterrows():
        folium.Marker([row.lat, row.lon], 
                      popup=folium.Popup(row.name, max_width=200),
                      icon=folium.Icon(color="gray")).add_to(mc)
    
    # 경로 지점들 마커
    current_order = st.session_state.get("order", stops)
    for idx, (x, y) in enumerate(snapped, 1):
        if idx <= len(current_order):
            place_name = current_order[idx - 1]
        else:
            place_name = f"지점 {idx}"
            
        folium.Marker([y, x],
                      icon=folium.Icon(color="red", icon="flag"),
                      tooltip=f"{idx}. {place_name}",
                      popup=folium.Popup(f"<b>{idx}. {place_name}</b>", max_width=200)
        ).add_to(m)
    
    # 경로 라인 + 구간 번호 (모든 기능 보존!)
    if st.session_state.get("segments"):
        palette = ["#4285f4", "#34a853", "#ea4335", "#fbbc04", "#9c27b0", "#ff9800"]
        segments = st.session_state["segments"]
        for i in range(len(segments), 0, -1):
            seg = segments[i - 1]
            folium.PolyLine([(pt[1], pt[0]) for pt in seg],
                            color=palette[(i - 1) % len(palette)], 
                            weight=5, 
                            opacity=0.8
            ).add_to(m)
            
            # 구간 번호 표시 (중요한 기능!)
            if seg:
                mid = seg[len(seg) // 2]
                folium.map.Marker([mid[1], mid[0]],
                    icon=DivIcon(html=f"<div style='background:{palette[(i - 1) % len(palette)]};"
                                      "color:#fff;border-radius:50%;width:28px;height:28px;"
                                      "line-height:28px;text-align:center;font-weight:600;"
                                      "box-shadow:0 2px 4px rgba(0,0,0,0.3);'>"
                                      f"{i}</div>")
                ).add_to(m)
        
        # 지도 범위 조정
        try:
            pts = [pt for seg in segments for pt in seg if seg]
            if pts:
                m.fit_bounds([[min(p[1] for p in pts), min(p[0] for p in pts)],
                              [max(p[1] for p in pts), max(p[0] for p in pts)]])
        except:
            m.location = [clat, clon]
            m.zoom_start = 12
    else:
        m.location = [clat, clon]
        m.zoom_start = 12
    
    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=580, returned_objects=[])
    st.markdown("</div>", unsafe_allow_html=True)

# OpenAI 클라이언트 초기화
client = openai.OpenAI(api_key="sk-proj-CrnyAxHpjHnHg6wu4iuTFlMRW8yFgSaAsmk8rTKcAJrYkPocgucoojPeVZ-uARjei6wyEILHmgT3BlbkFJ2_tSjk8mGQswRVBPzltFNh7zXYrsTfOIT3mzESkqrz2vbUsCIw3O1a2I6txAACdi673MitM1UA4")

# ------------------------------
# ✅ GPT 가이드 (모든 기능 보존)
# ------------------------------
st.markdown('<div class="gpt-section">', unsafe_allow_html=True)
st.markdown('<div class="section-title">🏛️ AI 관광 가이드</div>', unsafe_allow_html=True)

# 자동 입력 버튼
if st.button("🔁 방문 순서 자동 입력"):
    st.session_state["auto_gpt_input"] = ", ".join(st.session_state.get("order", []))

# 메시지 상태 초기화
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# 입력 폼
with st.form("chat_form"):
    user_input = st.text_input("관광지명 쉼표로 구분", value=st.session_state.get("auto_gpt_input", ""))
    submitted = st.form_submit_button("관광지 정보 조회")

# GPT 호출 및 정보 표시 (모든 기능 보존!)
if submitted and user_input:
    current_order = st.session_state.get("order", [])
    if current_order:
        st.markdown("### ✨ 관광지별 소개 + 카페 추천")

        for place in current_order[:3]:
            matched = data[data['t_name'].str.contains(place, na=False)]

            # GPT 소개
            try:
                gpt_intro = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "당신은 청주 지역의 문화 관광지를 간단하게 소개하는 관광 가이드입니다. "},
                        {"role": "system", "content": "존댓말을 사용하세요."},
                        {"role": "user", "content": f"{place}를 두 문단 이내로 간단히 설명해주세요."}
                    ]
                ).choices[0].message.content
            except Exception as e:
                gpt_intro = f"❌ GPT 호출 실패: {place} 소개를 불러올 수 없어요."

            # 관광지 정보 카드
            st.markdown(f'''
            <div class="place-info">
                <div class="place-title">🏛️ {place}</div>
                <div class="place-content">{gpt_intro}</div>
            </div>
            ''', unsafe_allow_html=True)

            # 평점, 리뷰, 카페 정보 (모든 기능 보존!)
            if not matched.empty:
                # 평점
                t_value = matched['t_value'].dropna().unique()
                if len(t_value) > 0:
                    st.markdown(f"**📊 관광지 평점:** ⭐ {t_value[0]}")

                # 리뷰
                reviews = matched['t_review'].dropna().unique()
                reviews = [r for r in reviews if all(x not in r for x in ["없음", "없읍"])]
                if reviews:
                    st.markdown("**💬 방문자 리뷰**")
                    for r in reviews[:3]:
                        st.markdown(f"- \"{r}\"")

                # 카페 정보
                cafes = matched[['c_name', 'c_value', 'c_review']].drop_duplicates()
                cafe_info = format_cafes(cafes)
                
                st.markdown(f'''
                <div class="cafe-section">
                    {cafe_info}
                </div>
                ''', unsafe_allow_html=True)
            else:
                st.markdown(f'''
                <div class="cafe-section">
                    현재 이 관광지 주변에 등록된 카페 정보는 없어요.<br>
                    하지만 근처에 숨겨진 보석 같은 공간이 있을 수 있으니,<br>
                    지도를 활용해 천천히 걸어보시는 것도 추천드립니다 😊
                </div>
                ''', unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
