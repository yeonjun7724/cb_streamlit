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

# ─────────────────────────────────────────────
# 1) 페이지 & CSS
# ─────────────────────────────────────────────
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

# ✅ OpenAI API KEY 직접 변수
OPENAI_API_KEY = "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"
client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────
# 2) 데이터 로드
# ─────────────────────────────────────────────
gdf      = gpd.read_file("cb_tour.shp").to_crs(epsg=4326)
gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
boundary = gpd.read_file("cb_shp.shp").to_crs(epsg=4326)

# ─────────────────────────────────────────────
# 3) session_state 초기화
# ─────────────────────────────────────────────
if "order" not in st.session_state: st.session_state.order = []
if "segments" not in st.session_state: st.session_state.segments = []
if "duration" not in st.session_state: st.session_state.duration = 0.0
if "distance" not in st.session_state: st.session_state.distance = 0.0
if "chat_messages" not in st._
