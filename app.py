import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import osmnx as ox
import requests
from shapely.geometry import Point
from streamlit_folium import st_folium
from openai import OpenAI
import math

# ✅ 👉 Mapbox 토큰 직접 변수로
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"

# ✅ 👉 GPT Key는 secrets.toml에서 안전하게 불러오기
client = OpenAI(api_key=st.secrets["openai"]["api_key"])

# ✅ 데이터 로드
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()

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

# ✅ 카페 포맷 함수
def format_cafes(cafes_df):
    cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
    result = []
    if len(cafes_df) == 0:
        return "☕ 현재 이 관광지 주변에 등록된 카페 정보가 없어요.\n근처 숨은 공간을 걸어보세요 😊"
    elif len(cafes_df) == 1:
        row = cafes_df.iloc[0]
        if all(x not in row["c_review"] for x in ["없음", "없읍"]):
            return f"☕ **추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})\n“{row['c_review']}”"
        else:
            return f"☕ **추천 카페**\n\n- **{row['c_name']}** (⭐ {row['c_value']})"
    else:
        grouped = cafes_df.groupby(['c_name', 'c_value'])
        result.append("☕ **주변에 이런 카페들이 있어요** 🌼\n")
        for (name, value), group in grouped:
            reviews = group['c_review'].dropna().unique()
            reviews = [r for r in reviews if all(x not in r for x in ["없음", "없읍"])]
            top_reviews = reviews[:3]
            if top_reviews:
                review_text = "\n".join([f"“{r}”" for r in top_reviews])
                result.append(f"- **{name}** (⭐ {value})\n{review_text}")
            else:
                result.append(f"- **{name}** (⭐ {value})")
        return "\n\n".join(result)

# ✅ 스타일
st.set_page_config(page_title="청주시 GPT 가이드", layout="wide")
st.markdown("""
<style>
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; background: #f9fafb; color: #333; }
  .small-text { font-size: 14px; color: #666; }
  .bold-number { font-size: 20px; font-weight: 600; }
  .visit-list { font-size: 14px; margin: 2px 0; }
</style>
""", unsafe_allow_html=True)
st.markdown("<h2 style='text-align:center;'>📍 청주시 경로 & GPT 가이드</h2>", unsafe_allow_html=True)

col_left, col_map, col_gpt = st.columns([1.5, 3, 2], gap="large")

# ------------------------------
# 🚗 경로 설정 + KPI + 방문 순서
# ------------------------------
with col_left:
    st.subheader("🚗 경로 설정")
    mode = st.radio("이동 모드", ["driving","walking"], horizontal=True)
    start = st.selectbox("출발지", gdf["name"].dropna().unique())
    wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
    col_btn1, col_btn2 = st.columns(2)
    create_clicked = col_btn1.button("✅ 경로 생성")
    clear_clicked = col_btn2.button("🚫 초기화")
    st.markdown("---")
    st.markdown("<div class='small-text'>🔢 방문 순서</div>", unsafe_allow_html=True)
    if st.session_state["order"]:
        for i, name in enumerate(st.session_state["order"], 1):
            st.markdown(f"<div class='visit-list'>{i}. {name}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='visit-list'>경로가 없습니다.</div>", unsafe_allow_html=True)
    st.markdown("<div class='small-text'>⏱️ 예상 소요 시간</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='bold-number'>{st.session_state['duration']:.1f} 분</div>", unsafe_allow_html=True)
    st.markdown("<div class='small-text'>📏 예상 이동 거리</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='bold-number'>{st.session_state['distance']:.2f} km</div>", unsafe_allow_html=True)

# ------------------------------
# 🗺️ 지도
# ------------------------------
with col_map:
    ctr = boundary.geometry.centroid
    clat, clon = float(ctr.y.mean()), float(ctr.x.mean())
    if math.isnan(clat): clat, clon = 36.64, 127.48

    @st.cache_data
    def load_graph(lat, lon):
        return ox.graph_from_point((lat, lon), dist=3000, network_type="all")
    G = load_graph(clat, clon)

    stops = [start] + wps
    snapped = []
    for nm in stops:
        row = gdf[gdf["name"] == nm].iloc[0]
        lon, lat = row.lon, row.lat
        node_id = ox.distance.nearest_nodes(G, lon, lat)
        node_data = G.nodes[node_id]
        snapped.append((node_data['x'], node_data['y']))

    if clear_clicked:
        for k in ["segments","order","duration","distance"]:
            st.session_state.pop(k, None)

    if create_clicked and len(snapped) >= 2:
        coords = ";".join([f"{x},{y}" for x, y in snapped])
        url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coords}" if len(snapped) > 2 \
            else f"https://api.mapbox.com/directions/v5/mapbox/{mode}/{coords}"
        key = "trips" if len(snapped) > 2 else "routes"
        params = {
            "geometries": "geojson", "overview": "full",
            "source": "first", "destination": "last", "roundtrip": "false",
            "access_token": MAPBOX_TOKEN
        } if len(snapped) > 2 else {
            "geometries": "geojson", "overview": "full", "access_token": MAPBOX_TOKEN
        }
        r = requests.get(url, params=params)
        data_resp = r.json() if r.status_code == 200 else {}
        if key in data_resp and data_resp[key]:
            route = data_resp[key][0]
            st.session_state["segments"] = [route["geometry"]["coordinates"]]
            st.session_state["duration"] = route["duration"] / 60
            st.session_state["distance"] = route["distance"] / 1000
            st.session_state["order"] = stops
        else:
            st.warning("❌ 경로 생성 실패!")

    m = folium.Map(location=[clat, clon], zoom_start=12)
    folium.GeoJson(boundary).add_to(m)
    mc = MarkerCluster().add_to(m)
    for _, row in gdf.iterrows():
        folium.Marker([row.lat, row.lon], popup=row.name).add_to(mc)
    for idx, ((x, y), name) in enumerate(zip(snapped, st.session_state.get("order", stops)), 1):
        folium.Marker([y, x], tooltip=f"{idx}. {name}",
                      icon=folium.Icon(color="#008EAB", icon="flag")).add_to(m)
    if st.session_state["segments"]:
        for seg in st.session_state["segments"]:
            folium.PolyLine([(pt[1], pt[0]) for pt in seg], color="red").add_to(m)
    st_folium(m, width="100%", height=500)

# ------------------------------
# 💬 GPT 가이드
# ------------------------------
with col_gpt:
    st.subheader("🏛️ GPT 관광 가이드")
    if st.button("🔁 방문 순서 가져오기"):
        st.session_state["auto_gpt_input"] = ", ".join(st.session_state.get("order", []))
    with st.form("chat_form"):
        user_input = st.text_input("관광지 쉼표로", value=st.session_state.get("auto_gpt_input", ""))
        submitted = st.form_submit_button("보내기")
    if submitted and user_input:
        st.session_state["messages"].append({"role": "user", "content": user_input})
        with st.spinner("청주의 아름다움을 정리 중입니다..."):
            places = [p.strip() for p in user_input.split(',') if p.strip()]
            blocks = []
            weather_intro = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "청주 관광 가이드"},
                    {"role": "user", "content": "청주 날씨, 추천 복장, 팁, 계절 알려줘"}
                ]
            ).choices[0].message.content
            blocks.append(f"🌤️ {weather_intro}")

            for place in places:
                matched = data[data['t_name'].str.contains(place, na=False)]
                place_intro = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "감성적인 청주 관광 가이드"},
                        {"role": "user", "content": f"{place} 역사, 계절, 포토스팟, 코멘트"}
                    ]
                ).choices[0].message.content
                if not matched.empty:
                    cafes = matched[['c_name','c_value','c_review']].drop_duplicates()
                    cafe_info = format_cafes(cafes)
                else:
                    cafe_info = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "청주 카페 추천 가이드"},
                            {"role": "user", "content": f"{place} 주변 카페 추천해줘"}
                        ]
                    ).choices[0].message.content

                blocks.append(f"🏛️ **{place}**\n\n{place_intro}\n\n{cafe_info}")
            final_response = "\n\n".join(blocks)
            st.session_state["messages"].append({"role": "assistant", "content": final_response})

    for msg in st.session_state["messages"][1:]:
        align = "right" if msg["role"] == "user" else "left"
        bg = "#dcf8c6" if msg["role"] == "user" else "#fff"
        st.markdown(f"<div style='text-align:{align};background:{bg};padding:8px;border-radius:10px;margin-bottom:6px'>{msg['content']}</div>", unsafe_allow_html=True)
