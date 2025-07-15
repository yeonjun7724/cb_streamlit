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
# 1) 페이지 설정 & 개선된 CSS
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="청주시 경유지 최적 경로", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700&display=swap');
    
    /* 전체 배경 */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
    }
    
    /* 메인 컨테이너 */
    .main .block-container {
        padding: 2rem 1rem;
        max-width: 1400px;
        background: rgba(255, 255, 255, 0.95);
        border-radius: 20px;
        margin: 2rem auto;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        backdrop-filter: blur(10px);
    }
    
    /* 폰트 설정 */
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #2c3e50;
    }
    
    /* 타이틀 */
    .main-title {
        background: linear-gradient(45deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 2rem;
        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* 카드 디자인 */
    .modern-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(248,250,252,0.9) 100%);
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        border: 1px solid rgba(255,255,255,0.2);
        backdrop-filter: blur(10px);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        margin-bottom: 1.5rem;
    }
    
    .modern-card:hover {
        transform: translateY(-8px);
        box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        border-color: rgba(102, 126, 234, 0.3);
    }
    
    /* 메트릭 카드 */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        text-align: center;
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
        transition: all 0.3s ease;
        border: none;
    }
    
    .metric-card:hover {
        transform: translateY(-5px) scale(1.02);
        box-shadow: 0 15px 40px rgba(102, 126, 234, 0.4);
    }
    
    .metric-number {
        font-size: 2rem;
        font-weight: 700;
        margin: 0.5rem 0;
        text-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    .metric-label {
        font-size: 1rem;
        opacity: 0.9;
        font-weight: 500;
    }
    
    /* 버튼 스타일 */
    .stButton > button {
        width: 100%;
        border: none;
        border-radius: 12px;
        font-weight: 600;
        padding: 0.8rem 1.5rem;
        font-size: 1rem;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }
    
    .primary-btn {
        background: linear-gradient(45deg, #667eea, #764ba2) !important;
        color: white !important;
    }
    
    .primary-btn:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4) !important;
    }
    
    .danger-btn {
        background: linear-gradient(45deg, #ff6b6b, #ee5a52) !important;
        color: white !important;
    }
    
    .danger-btn:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(255, 107, 107, 0.4) !important;
    }
    
    /* 섹션 헤더 */
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #2c3e50;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* 방문 순서 리스트 */
    .visit-order {
        background: linear-gradient(135deg, #f8f9ff 0%, #e8f0ff 100%);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
        transition: all 0.3s ease;
    }
    
    .visit-order:hover {
        background: linear-gradient(135deg, #e8f0ff 0%, #d0e0ff 100%);
        transform: translateX(5px);
    }
    
    .order-number {
        display: inline-block;
        background: linear-gradient(45deg, #667eea, #764ba2);
        color: white;
        width: 24px;
        height: 24px;
        border-radius: 50%;
        text-align: center;
        line-height: 24px;
        font-weight: 600;
        font-size: 0.8rem;
        margin-right: 0.5rem;
    }
    
    /* 지도 컨테이너 */
    .map-container {
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 12px 40px rgba(0,0,0,0.15);
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    /* 라디오 버튼 커스텀 */
    .stRadio > div > div > div > label {
        background: rgba(102, 126, 234, 0.1);
        border-radius: 8px;
        padding: 0.5rem 1rem;
        margin: 0.2rem;
        transition: all 0.3s ease;
        border: 2px solid transparent;
    }
    
    .stRadio > div > div > div > label:hover {
        background: rgba(102, 126, 234, 0.2);
        border-color: rgba(102, 126, 234, 0.3);
    }
    
    /* 셀렉트박스 커스텀 */
    .stSelectbox > div > div > div {
        border-radius: 8px;
        border: 2px solid rgba(102, 126, 234, 0.2);
        transition: all 0.3s ease;
    }
    
    .stSelectbox > div > div > div:focus-within {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    /* 멀티셀렉트 커스텀 */
    .stMultiSelect > div > div > div {
        border-radius: 8px;
        border: 2px solid rgba(102, 126, 234, 0.2);
        transition: all 0.3s ease;
    }
    
    .stMultiSelect > div > div > div:focus-within {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    /* 빈 상태 메시지 */
    .empty-state {
        text-align: center;
        color: #64748b;
        font-style: italic;
        padding: 2rem;
        background: rgba(102, 126, 234, 0.05);
        border-radius: 12px;
        border: 2px dashed rgba(102, 126, 234, 0.2);
    }
    
    /* 반응형 디자인 */
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem 0.5rem;
            margin: 1rem;
        }
        
        .main-title {
            font-size: 2rem;
        }
        
        .metric-number {
            font-size: 1.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)

MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ──────────────────────────────────────────────
# 2) 데이터 로드
# ──────────────────────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ──────────────────────────────────────────────
# 3) 헤더
# ──────────────────────────────────────────────
st.markdown("<h1 class='main-title'>📍 청주시 경유지 최적 경로</h1>", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 4) 메트릭 카드
# ──────────────────────────────────────────────
dur = st.session_state.get("duration", 0.0)
dist = st.session_state.get("distance", 0.0)

col1, col2 = st.columns(2, gap="medium")

with col1:
    st.markdown(f"""
    <div class='metric-card'>
        <div class='metric-label'>⏱️ 예상 소요 시간</div>
        <div class='metric-number'>{dur:.1f} 분</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class='metric-card'>
        <div class='metric-label'>📏 예상 이동 거리</div>
        <div class='metric-number'>{dist:.2f} km</div>
    </div>
    """, unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 5) 메인 레이아웃
# ──────────────────────────────────────────────
col_ctrl, col_order, col_map = st.columns([1.5, 1, 4], gap="large")

# --- 컨트롤 패널
with col_ctrl:
    st.markdown("<div class='modern-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>🚗 경로 설정</div>", unsafe_allow_html=True)
    
    mode = st.radio("이동 모드", ["driving", "walking"], horizontal=True)
    start = st.selectbox("🎯 출발지", gdf["name"].dropna().unique())
    wps = st.multiselect("📍 경유지", [n for n in gdf["name"].dropna().unique() if n != start])
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # 버튼들
    create_clicked = st.button("✅ 경로 생성", key="run", help="선택한 경유지들의 최적 경로를 생성합니다")
    clear_clicked = st.button("🚫 초기화", key="clear", help="모든 설정을 초기화합니다")

# --- 방문 순서
with col_order:
    st.markdown("<div class='modern-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>🔢 방문 순서</div>", unsafe_allow_html=True)
    
    if "order" in st.session_state:
        for i, name in enumerate(st.session_state.order, 1):
            st.markdown(f"""
            <div class='visit-order'>
                <span class='order-number'>{i}</span>
                <strong>{name}</strong>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class='empty-state'>
            경로를 생성하면<br>방문 순서가 여기에 표시됩니다
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

# --- 지도
with col_map:
    st.markdown("<div class='modern-card' style='padding: 8px;'>", unsafe_allow_html=True)
    
    # 지도 중심점 계산
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): 
        clat, clon = 36.64, 127.48

    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    
    G = load_graph(clat, clon)
    edges = ox.graph_to_gdfs(G, nodes=False)

    # 선택된 지점들 처리
    stops = [start] + wps
    snapped = []
    for nm in stops:
        r = gdf[gdf["name"] == nm].iloc[0]
        pt = Point(r.lon, r.lat)
        edges["d"] = edges.geometry.distance(pt)
        ln = edges.loc[edges["d"].idxmin()]
        sp = ln.geometry.interpolate(ln.geometry.project(pt))
        snapped.append((sp.x, sp.y))

    # 초기화 버튼 처리
    if clear_clicked:
        for k in ["segments", "order", "duration", "distance"]:
            st.session_state.pop(k, None)

    # 경로 생성 처리
    if create_clicked and len(snapped) >= 2:
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
            data = r.json() if r.status_code == 200 else {}
            
            if data.get(key):
                leg = data[key][0]
                segs.append(leg["geometry"]["coordinates"])
                td += leg["duration"]
                tl += leg["distance"]
        
        if segs:
            st.session_state.order = stops
            st.session_state.duration = td / 60
            st.session_state.distance = tl / 1000
            st.session_state.segments = segs

    # 지도 생성
    m = folium.Map(
        location=[clat, clon], 
        tiles='CartoDB positron', 
        zoom_start=12,
        prefer_canvas=True
    )

    # 경계선 추가
    folium.GeoJson(
        boundary, 
        style_function=lambda feature: {
            "color": "#667eea",
            "weight": 3,
            "dashArray": "8,4",
            "fillOpacity": 0.1,
            "fillColor": "#667eea"
        }
    ).add_to(m)

    # 관광지 마커 클러스터
    mc = MarkerCluster(
        name="관광지",
        overlay=True,
        control=True
    ).add_to(m)
    
    for _, row in gdf.iterrows():
        folium.Marker(
            [row.lat, row.lon], 
            popup=folium.Popup(row.name, max_width=200),
            tooltip=row.name,
            icon=folium.Icon(color="lightgray", icon="info-sign", prefix="glyphicon")
        ).add_to(mc)

    # 선택된 지점 마커
    for idx, (x, y) in enumerate(snapped, 1):
        color = "red" if idx == 1 else "blue" if idx == len(snapped) else "green"
        icon_name = "play" if idx == 1 else "stop" if idx == len(snapped) else "record"
        
        folium.Marker(
            [y, x],
            icon=folium.Icon(color=color, icon=icon_name, prefix="glyphicon"),
            popup=folium.Popup(f"{idx}. {st.session_state.get('order', stops)[idx-1]}", max_width=200),
            tooltip=f"{idx}. {st.session_state.get('order', stops)[idx-1]}"
        ).add_to(m)

    # 경로 라인 그리기
    if "segments" in st.session_state:
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FECA57", "#FF9FF3"]
        
        for i in range(len(st.session_state.segments), 0, -1):
            seg = st.session_state.segments[i-1]
            color = colors[(i-1) % len(colors)]
            
            # 경로 라인
            folium.PolyLine(
                [(pt[1], pt[0]) for pt in seg],
                color=color,
                weight=5,
                opacity=0.8,
                popup=f"구간 {i}"
            ).add_to(m)
            
            # 구간 번호 마커
            mid = seg[len(seg)//2]
            folium.Marker(
                [mid[1], mid[0]],
                icon=DivIcon(
                    html=f"""
                    <div style='
                        background: {color};
                        color: white;
                        border-radius: 50%;
                        width: 30px;
                        height: 30px;
                        line-height: 30px;
                        text-align: center;
                        font-weight: bold;
                        font-size: 14px;
                        border: 2px solid white;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    '>{i}</div>
                    """,
                    icon_size=(30, 30),
                    icon_anchor=(15, 15)
                )
            ).add_to(m)
        
        # 지도 범위 조정
        pts = [pt for seg in st.session_state.segments for pt in seg]
        m.fit_bounds([
            [min(p[1] for p in pts), min(p[0] for p in pts)],
            [max(p[1] for p in pts), max(p[0] for p in pts)]
        ])
    else:
        m.location = [clat, clon]
        m.zoom_start = 12

    # 레이어 컨트롤 추가
    folium.LayerControl().add_to(m)
    
    # 지도 표시
    st.markdown("<div class='map-container'>", unsafe_allow_html=True)
    st_folium(m, width="100%", height=650, returned_data=["last_object_clicked"])
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

# CSS 인젝션으로 버튼 스타일 적용
st.markdown("""
<script>
document.addEventListener('DOMContentLoaded', function() {
    const buttons = document.querySelectorAll('.stButton > button');
    if (buttons[0]) {
        buttons[0].classList.add('primary-btn');
    }
    if (buttons[1]) {
        buttons[1].classList.add('danger-btn');
    }
});
</script>
""", unsafe_allow_html=True)
