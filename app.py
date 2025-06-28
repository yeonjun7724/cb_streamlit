import geopandas as gpd
import folium
from streamlit_folium import st_folium
import streamlit as st
import requests

# Shapefile 읽기
gdf = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"] = gdf.geometry.x
gdf["lat"] = gdf.geometry.y

st.title("📍 포인트 멀티선택 → Mapbox 라우팅")

# 멀티셀렉트로 선택
options = gdf.index.tolist()
selected = st.multiselect("선택할 포인트 ID", options)

selected_coords = [(gdf.loc[idx, "lon"], gdf.loc[idx, "lat"]) for idx in selected]

st.write("✅ 선택된 포인트:", selected_coords)

# 초기 지도
m = folium.Map(location=[gdf["lat"].mean(), gdf["lon"].mean()], zoom_start=12)

# 모든 포인트
for idx, row in gdf.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"ID: {idx}"
    ).add_to(m)

# 선택된 포인트
for lon, lat in selected_coords:
    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color="green",
        fill=True,
        fill_opacity=1.0
    ).add_to(m)

st_folium(m, height=600, width=800)

# Directions API
MAPBOX_TOKEN = "YOUR_MAPBOX_TOKEN"

if st.button("✅ 확인 (라우팅)"):
    if len(selected_coords) >= 2:
        coords_str = ";".join([f"{lon},{lat}" for lon, lat in selected_coords])
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "access_token": MAPBOX_TOKEN
        }

        response = requests.get(url, params=params)
        result = response.json()
        st.write("📦 API 응답:", result)

        if "routes" in result:
            route = result["routes"][0]["geometry"]["coordinates"]
            st.success(f"✅ 경로 생성됨! 점 수: {len(route)}")

            m2 = folium.Map(
                location=[selected_coords[0][1], selected_coords[0][0]],
                zoom_start=12
            )

            for lon, lat in selected_coords:
                folium.Marker(
                    location=[lat, lon],
                    icon=folium.Icon(color="green")
                ).add_to(m2)

            folium.PolyLine(
                [(lat, lon) for lon, lat in route],
                color="blue",
                weight=4,
                opacity=0.7
            ).add_to(m2)

            st_folium(m2, height=600, width=800)
        else:
            st.warning(f"❌ 경로 없음: {result.get('message', 'Unknown error')}")
    else:
        st.warning("2개 이상 포인트 선택 필요!")
