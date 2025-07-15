import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
from shapely.geometry import Point
import osmnx as ox
import requests, math
from streamlit_folium import st_folium
import pandas as pd
import re
from openai import OpenAI

# ──────────────────────────────────────────────
# 페이지 설정 및 CSS
# ──────────────────────────────────────────────
st.set_page_config(page_title="청주시 통합 관광 시스템", layout="wide")

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
  .stTabs [data-baseweb="tab-list"] {
    gap: 24px;
  }
  .stTabs [data-baseweb="tab"] {
    height: 50px;
    background-color: white;
    border-radius: 8px;
    color: #333;
    font-weight: 600;
  }
  .stTabs [aria-selected="true"] {
    background-color: #00C9A7;
    color: white;
  }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 메인 헤더
# ──────────────────────────────────────────────
st.markdown("<h1 style='text-align:center; padding:16px 0;'>🏛️ 청주시 통합 관광 시스템</h1>", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 탭 생성
# ──────────────────────────────────────────────
tab1, tab2 = st.tabs(["📍 경로 최적화", "🏞️ 문화 관광가이드"])

# ──────────────────────────────────────────────
# 탭 1: 경로 최적화
# ──────────────────────────────────────────────
with tab1:
    # 데이터 로드
    try:
        gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
        gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
        boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
        
        MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"
        
        # 메트릭
        dur = st.session_state.get("duration", 0.0)
        dist = st.session_state.get("distance", 0.0)
        m1, m2 = st.columns(2, gap="small")

        with m1:
            st.markdown("<div class='card' style='text-align:center;'>", unsafe_allow_html=True)
            st.markdown("<h4>⏱️ 예상 소요 시간</h4>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:8px;'>{dur:.1f} 분</h2>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with m2:
            st.markdown("<div class='card' style='text-align:center;'>", unsafe_allow_html=True)
            st.markdown("<h4>📏 예상 이동 거리</h4>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:8px;'>{dist:.2f} km</h2>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # 레이아웃: 컨트롤 | 순서 | 지도
        col_ctrl, col_order, col_map = st.columns([1.5,1,4], gap="large")

        # 컨트롤
        with col_ctrl:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("🚗 경로 설정")
            mode = st.radio("이동 모드", ["driving","walking"], horizontal=True)
            start = st.selectbox("출발지", gdf["name"].dropna().unique())
            wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n!=start])
            st.markdown("</div>", unsafe_allow_html=True)

            create_clicked = st.button("✅ 경로 생성", key="run")
            clear_clicked = st.button("🚫 초기화", key="clear")

        # 방문 순서
        with col_order:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("🔢 방문 순서")
            if "order" in st.session_state:
                for i,name in enumerate(st.session_state.order,1):
                    st.markdown(f"<p style='margin:4px 0;'><strong>{i}.</strong> {name}</p>", unsafe_allow_html=True)
            else:
                st.markdown("<p style='color:#999;'>경로 생성 후 순서 표시됩니다.</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # 지도
        with col_map:
            ctr = boundary.geometry.centroid
            clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
            if math.isnan(clat): 
                clat, clon = 36.64, 127.48

            @st.cache_data
            def load_graph(lat, lon):
                return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
            
            G = load_graph(clat, clon)
            edges = ox.graph_to_gdfs(G, nodes=False)

            stops = [start] + wps
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
                    r = requests.get(url, params=params)
                    data = r.json() if r.status_code==200 else {}
                    if data.get(key):
                        leg = data[key][0]
                        segs.append(leg["geometry"]["coordinates"])
                        td += leg["duration"]; tl += leg["distance"]
                if segs:
                    st.session_state.order = stops
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
                    icon=folium.Icon(color="blue",icon="flag"),
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
            
    except Exception as e:
        st.error(f"지도 데이터를 불러올 수 없습니다: {e}")
        st.info("cb_tour.shp, cb_shp.shp 파일이 필요합니다.")

# ──────────────────────────────────────────────
# 탭 2: 문화 관광가이드
# ──────────────────────────────────────────────
with tab2:
    # OpenAI 클라이언트 초기화
    try:
        client = OpenAI(api_key=st.secrets["sk-proj-CrnyAxHpjHnHg6wu4iuTFlMRW8yFgSaAsmk8rTKcAJrYkPocgucoojPeVZ-uARjei6wyEILHmgT3BlbkFJ2_tSjk8mGQswRVBPzltFNh7zXYrsTfOIT3mzESkqrz2vbUsCIw3O1a2I6txAACdi673MitM1UA4"])
        
        # CSV 데이터 로드
        try:
            data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()
        except:
            st.error("cj_data_final.csv 파일을 찾을 수 없습니다.")
            st.stop()

        # 카페 포맷 함수
        def format_cafes(cafes_df):
            cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
            result = []

            if len(cafes_df) == 0:
                return ("☕ 현재 이 관광지 주변에 등록된 카페 정보는 없어요.  \n"
                        "하지만 근처에 숨겨진 보석 같은 공간이 있을 수 있으니,  \n"
                        "지도를 활용해 천천히 걸어보시는 것도 추천드립니다 😊")

            elif len(cafes_df) == 1:
                row = cafes_df.iloc[0]
                if all(x not in row["c_review"] for x in ["없음", "없읍"]):
                    return f"""☕ **주변 추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})  \n"{row['c_review']}""""
                else:
                    return f"""☕ **주변 추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})"""

            else:
                grouped = cafes_df.groupby(['c_name', 'c_value'])
                result.append("☕ **주변에 이런 카페들이 있어요** 🌼\n")
                for (name, value), group in grouped:
                    reviews = group['c_review'].dropna().unique()
                    reviews = [r for r in reviews if all(x not in r for x in ["없음", "없읍"])]
                    top_reviews = reviews[:3]

                    if top_reviews:
                        review_text = "\n".join([f""{r}"" for r in top_reviews])
                        result.append(f"- **{name}** (⭐ {value})  \n{review_text}")
                    else:
                        result.append(f"- **{name}** (⭐ {value})")

                return "\n\n".join(result)

        # 초기 세션 설정 (chat_messages로 키 변경하여 탭1과 충돌 방지)
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = [
                {"role": "system", "content": "당신은 청주 문화유산을 소개하는 감성적이고 공손한 말투의 관광 가이드 챗봇입니다."}
            ]

        st.markdown("<h2 style='text-align:center;'>🏞️ 청주 문화 관광가이드</h2>", unsafe_allow_html=True)

        # 이전 메시지 출력 (시스템 메시지 제외)
        for msg in st.session_state.chat_messages[1:]:
            if msg["role"] == "user":
                st.markdown(f"<div style='text-align: right; background-color: #dcf8c6; border-radius: 10px; padding: 12px; margin: 8px 0;'>{msg['content']}</div>", unsafe_allow_html=True)
            elif msg["role"] == "assistant":
                st.markdown(f"<div style='text-align: left; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 12px; margin: 8px 0;'>{msg['content']}</div>", unsafe_allow_html=True)

        st.markdown("---")

        # 입력 폼 처리
        with st.form("chat_form"):
            user_input = st.text_input("지도에서 선택한 관광지들을 여기에 입력해주세요! (쉼표(,)로 구분해 주세요. 예: 청주 신선주, 청주 청녕각)")
            submitted = st.form_submit_button("보내기", use_container_width=True)

        if submitted and user_input:
            st.session_state.chat_messages.append({"role": "user", "content": user_input})

            with st.spinner("청주의 아름다움을 정리 중입니다..."):
                places = [p.strip() for p in user_input.split(',') if p.strip()]
                response_blocks = []

                # GPT 서론 생성
                weather_intro = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "당신은 청주 관광을 소개하는 감성적이고 공손한 여행 가이드입니다."},
                        {"role": "user", "content": "오늘 청주의 날씨, 추천 복장, 걷기 좋은 시간대, 소소한 여행 팁, 계절 분위기 등을 이모지와 함께 따뜻한 말투로 소개해 주세요. 관광지 소개 전 서론으로 쓸 내용입니다."}
                    ]
                ).choices[0].message.content
                response_blocks.append(f"🌤️ {weather_intro}")

                for place in places:
                    matched = data[data['t_name'].str.contains(place, na=False)]

                    gpt_place_response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "당신은 청주 문화유산을 소개하는 감성적이고 따뜻한 말투의 공손한 관광 가이드입니다. 이모지도 풍부하게 사용하세요."},
                            {"role": "user", "content": f"""
여행자에게 설렘이 느껴지도록, 따뜻하고 공손한 말투로 {place}를 소개해 주세요 ✨  
✔️ 역사적인 배경,  
✔️ 방문 시의 분위기와 계절의 어울림 🍃🌸  
✔️ 인근 포토스팟 📸  
✔️ 여행자에게 추천하는 감성적인 코멘트 🌿  
문단마다 이모지를 활용해 생동감 있게 작성해 주세요. 줄바꿈도 적절히 해 주세요.
"""}
                        ]
                    ).choices[0].message.content

                    if not matched.empty:
                        cafes = matched[['c_name', 'c_value', 'c_review']].drop_duplicates()
                        cafe_info = format_cafes(cafes)

                        t_value = matched['t_value'].dropna().unique()
                        score_text = f"\n\n📊 **관광지 평점**: ⭐ {t_value[0]}" if len(t_value) > 0 else ""

                        reviews = matched['t_review'].dropna().unique()
                        reviews = [r for r in reviews if all(x not in r for x in ["없음", "없읍"])]
                        if len(reviews) > 0:
                            top_reviews = list(reviews)[:3]
                            review_text = "\n".join([f""{r}"" for r in top_reviews])
                            review_block = f"\n\n💬 **방문자 리뷰 중 일부**\n{review_text}"
                        else:
                            review_block = ""
                    else:
                        score_text = ""
                        review_block = ""
                        cafe_info = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "당신은 청주 지역의 감성적인 관광 가이드입니다. 공손하고 따뜻한 말투로 주변 카페를 추천하세요."},
                                {"role": "user", "content": f"{place} 주변에 어울리는 카페를 2~3곳 추천해 주세요. 이름, 분위기, 어떤 사람에게 잘 어울리는지 등을 감성적으로 설명해 주세요. 이모지와 줄바꿈도 사용해 주세요."}
                            ]
                        ).choices[0].message.content

                    full_block = f"---\n\n<h2 style='font-size: 24px; font-weight: bold;'>🏛️ {place}</h2>{score_text}\n\n{gpt_place_response}{review_block}\n\n{cafe_info}"
                    response_blocks.append(full_block)

                final_response = "\n\n".join(response_blocks)
                st.session_state.chat_messages.append({"role": "assistant", "content": final_response})

            # 페이지 새로고침하여 새 메시지 표시
            st.rerun()
            
    except Exception as e:
        st.error(f"OpenAI API 키가 설정되지 않았습니다: {e}")
        st.info("Streamlit secrets에 OPENAI_API_KEY를 설정해주세요.")

# ──────────────────────────────────────────────
# 사이드바 정보
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📋 사용 가이드")
    st.markdown("""
    **경로 최적화 탭:**
    - 출발지와 경유지를 선택하세요
    - 이동 모드를 설정하세요
    - 경로 생성 버튼을 클릭하세요
    
    **문화 관광가이드 탭:**
    - 관광지 이름을 쉼표로 구분하여 입력하세요
    - AI가 상세한 정보를 제공합니다
    """)
    
    st.markdown("### ⚠️ 필요한 파일")
    st.markdown("""
    - `cb_tour.shp` (관광지 데이터)
    - `cb_shp.shp` (청주시 경계)
    - `cj_data_final.csv` (문화유산 정보)
    - OpenAI API 키 설정
    """)
