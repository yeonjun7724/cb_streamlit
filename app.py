import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import osmnx as ox
import requests
from streamlit_folium import st_folium
from openai import OpenAI
import math

# ──────────────────────────────
# ✅ API KEY 직접 전달
# ──────────────────────────────
MAPBOX_TOKEN = "pk.eyJ1Ijoia2lteWVvbmp1biIsImEiOiJjbWM5cTV2MXkxdnJ5MmlzM3N1dDVydWwxIn0.rAH4bQmtA-MmEuFwRLx32Q"
client = OpenAI(api_key="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")

# ──────────────────────────────
# ✅ 데이터 로드
# ──────────────────────────────
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)
data = pd.read_csv("cj_data_final.csv", encoding="cp949").drop_duplicates()

# ──────────────────────────────
# ✅ session_state 초기화
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
# ✅ 카페 포맷 함수
# ──────────────────────────────
def format_cafes(cafes_df):
    cafes_df = cafes_df.drop_duplicates(subset=['c_name', 'c_value', 'c_review'])
    result = []
    if len(cafes_df) == 0:
        return "☕ 주변 카페 정보가 없어요. 숨은 보석 같은 공간을 걸어서 찾아보세요 😊"
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

# ──────────────────────────────
# ✅ 레이아웃 시작
# ──────────────────────────────
st.set_page_config(page_title="청주시 경유지 & GPT", layout="wide")

st.markdown("<h1 style='text-align:center;'>📍 청주시 경유지 & GPT 가이드</h1>", unsafe_allow_html=True)
col_left, col_right = st.columns([3, 1.5], gap="large")

# ------------------------------
# 🚗 좌측: 경유지 경로
# ------------------------------
with col_left:
    m1, m2 = st.columns(2, gap="small")
    with m1:
        st.markdown("⏱️ **예상 소요 시간**")
        st.subheader(f"{st.session_state['duration']:.1f} 분")
    with m2:
        st.markdown("📏 **예상 이동 거리**")
        st.subheader(f"{st.session_state['distance']:.2f} km")

    col_ctrl, col_order, col_map = st.columns([1.5, 1, 4], gap="large")

    with col_ctrl:
        st.subheader("🚗 경로 설정")
        mode = st.radio("이동 모드", ["driving","walking"], horizontal=True)
        start = st.selectbox("출발지", gdf["name"].dropna().unique())
        wps = st.multiselect("경유지", [n for n in gdf["name"].dropna().unique() if n != start])
        create_clicked = st.button("✅ 경로 생성")
        clear_clicked = st.button("🚫 초기화")

    with col_order:
        st.subheader("🔢 방문 순서")
        if st.session_state["order"]:
            for i, name in enumerate(st.session_state["order"], 1):
                st.markdown(f"{i}. {name}")
        else:
            st.markdown("🚫 경로 생성 후 표시됩니다.")

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
        st_folium(m, width="100%", height=600)

# ------------------------------
# 💬 우측: GPT 가이드
# ------------------------------
with col_right:
    st.subheader("🏛️ 청주 GPT 가이드")
    for msg in st.session_state["messages"][1:]:
        align = "right" if msg["role"] == "user" else "left"
        bg = "#dcf8c6" if msg["role"] == "user" else "#fff"
        st.markdown(
            f"<div style='text-align:{align};background:{bg};padding:8px;border-radius:10px;margin-bottom:6px'>{msg['content']}</div>",
            unsafe_allow_html=True)
    if st.button("🔁 방문 순서 가져오기"):
        route = st.session_state.get("order", [])
        st.session_state["auto_gpt_input"] = ", ".join(route) if route else ""
    with st.form("chat_form"):
        user_input = st.text_input("📍 관광지명을 쉼표로 입력하세요", value=st.session_state.get("auto_gpt_input", ""))
        submitted = st.form_submit_button("보내기")
    if submitted and user_input:
        st.session_state["messages"].append({"role": "user", "content": user_input})
        with st.spinner("청주 이야기 생성 중..."):
            places = [p.strip() for p in user_input.split(',') if p.strip()]
            blocks = []
            weather_intro = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "너는 청주 관광 가이드야."},
                    {"role": "user", "content": "청주 날씨, 산책 팁, 계절 분위기를 소개해줘."}
                ]
            ).choices[0].message.content
            blocks.append(f"🌤️ {weather_intro}")
            for place in places:
                matched = data[data['t_name'].str.contains(place, na=False)]
                place_intro = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "너는 따뜻한 청주 관광 가이드야."},
                        {"role": "user", "content": f"{place}의 역사, 계절 어울림, 포토스팟, 여행 팁을 감성적으로 소개해줘."}
                    ]
                ).choices[0].message.content
                cafe_info = format_cafes(matched[['c_name','c_value','c_review']]) if not matched.empty else \
                    client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "너는 청주 카페 추천 가이드야."},
                            {"role": "user", "content": f"{place} 주변 카페를 추천해줘."}
                        ]
                    ).choices[0].message.content
                blocks.append(f"🏛️ **{place}**\n\n{place_intro}\n\n{cafe_info}")
            final_response = "\n\n".join(blocks)
            st.session_state["messages"].append({"role": "assistant", "content": final_response})
