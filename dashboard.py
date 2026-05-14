import streamlit as st
import pandas as pd
import sqlite3, os, hashlib, secrets, io, base64, time
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Conditional import for MetaTrader5 (Windows only)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

st.set_page_config(page_title="APEX SUPREME", layout="wide", initial_sidebar_state="expanded")

# ── User authentication (from Streamlit Secrets) ─────────────────
def load_users():
    """Read users from st.secrets. Expected format:
    [users]
    user1_password = "hash1"
    user1_sub = "true"
    user2_password = "hash2"
    user2_sub = "true"
    """
    users = {}
    for key, value in st.secrets.get("users", {}).items():
        if key.endswith("_sub"):
            continue
        if key.endswith("_password"):
            user_id = key[:-9]  # remove "_password"
            users[user_id] = {
                "password_hash": value,
                "subscribed": st.secrets["users"].get(f"{user_id}_sub", "false") == "true"
            }
    return users

def verify_user(user_id, password):
    # Built‑in admin override
    ADMIN_USER = "apex_admin"
    ADMIN_PASS_HASH = hashlib.sha256("Donttrustnoone1.".encode()).hexdigest()
    
    if user_id == ADMIN_USER and hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASS_HASH:
        return True, True   # authenticated and subscribed
    
    # Otherwise check secrets as before
    users = load_users()
    user = users.get(user_id)
    if not user:
        return False, False
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return hashed == user["password_hash"], user["subscribed"]

# ── Session state ──────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None

# ── Login page ─────────────────────────────────────────────────
if not st.session_state.authenticated:
    st.title("🔐 APEX Terminal")
    tab1, tab2 = st.tabs(["Login", "Subscribe"])

    with tab1:
        with st.form("login"):
            user_id = st.text_input("User ID")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                ok, sub = verify_user(user_id, password)
                if ok and sub:
                    st.session_state.authenticated = True
                    st.session_state.user_id = user_id
                    st.rerun()
                elif ok and not sub:
                    st.error("Subscription inactive. Please renew.")
                else:
                    st.error("Invalid credentials")

    with tab2:
        st.write("## APEX Institutional Dashboard – $29/month")
        st.markdown("""
        - 📈 Equity curve & win‑rate tracking
        - 🕯️ Live XAUUSD chart with Fair Value Gaps (FVG)
        - 📡 Real‑time positions & pending orders monitor
        - 🧠 AI‑powered insights (confidence, RSI zones, trade lessons)
        - 📂 CSV export
        - 5 beautiful themes. No installation. Cancel anytime.
        """)
        st.markdown("[Subscribe Now →](https://buy.stripe.com/your_payment_link)")
        st.info("After payment, we will send you your login credentials within 2 hours.")
    st.stop()

# ── Database path per user ─────────────────────────────────────
USER_DB_DIR = "user_databases"
os.makedirs(USER_DB_DIR, exist_ok=True)
user_db_path = os.path.join(USER_DB_DIR, f"{st.session_state.user_id}.db")

def init_user_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute('''CREATE TABLE IF NOT EXISTS market_memory 
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
             symbol TEXT, type TEXT, gold_rsi REAL, dxy_trend INTEGER,
             yield_trend INTEGER, fvg_status INTEGER, vix_level REAL,
             volatility_index REAL, spread REAL, hour INTEGER,
             ai_confidence REAL, status TEXT, source TEXT,
             provider TEXT, reason TEXT, outcome INTEGER,
             profit REAL, commission REAL, swap REAL,
             ticket_id INTEGER, tp_ladder TEXT)''')

if not os.path.exists(user_db_path):
    init_user_db(user_db_path)

# ── Data loading (uses user_db_path) ────────────────────────────
@st.cache_data(ttl=15)
def load_user_data(db_path):
    if not os.path.exists(db_path):
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql("SELECT * FROM market_memory", conn)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    for col in df.columns:
        if df[col].dtype == 'float64': df[col] = df[col].fillna(0.0)
        elif df[col].dtype == 'int64': df[col] = df[col].fillna(-1)
        else: df[col] = df[col].fillna("")
    return df

def append_csv_to_db(uploaded_file, db_path):
    try:
        new_data = pd.read_csv(uploaded_file)
        required_cols = ['timestamp','symbol','type','outcome','profit']
        for col in required_cols:
            if col not in new_data.columns:
                new_data[col] = ''
        with sqlite3.connect(db_path) as conn:
            new_data.to_sql('market_memory', conn, if_exists='append', index=False)
        return True
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return False

# ── Themes ─────────────────────────────────────────────────────
THEMES = {
    "Dark (Default)": {
        "bg": "#131722", "card_bg": "#161a25", "text": "#d1d4dc", "accent": "#d4af37",
        "grid": "rgba(42,46,57,0.5)", "profit_green": "#00ff96", "loss_red": "#ff5050",
        "template": "plotly_dark", "candle_up": "#26a69a", "candle_down": "#ef5350"
    },
    "Light": {
        "bg": "#ffffff", "card_bg": "#f5f5f5", "text": "#1a1a1a", "accent": "#b8860b",
        "grid": "rgba(200,200,200,0.5)", "profit_green": "#008000", "loss_red": "#cc0000",
        "template": "plotly_white", "candle_up": "#008000", "candle_down": "#cc0000"
    },
    "Midnight Blue": {
        "bg": "#0a0e27", "card_bg": "#111540", "text": "#c8cdff", "accent": "#5b8def",
        "grid": "rgba(50,55,100,0.5)", "profit_green": "#00e676", "loss_red": "#ff5252",
        "template": "plotly_dark", "candle_up": "#00e676", "candle_down": "#ff5252"
    },
    "Forest": {
        "bg": "#0d1f0d", "card_bg": "#152a15", "text": "#c8e6c8", "accent": "#4caf50",
        "grid": "rgba(40,80,40,0.5)", "profit_green": "#69f0ae", "loss_red": "#ff8a80",
        "template": "plotly_dark", "candle_up": "#69f0ae", "candle_down": "#ff8a80"
    },
    "Solar": {
        "bg": "#1a0a00", "card_bg": "#2d1500", "text": "#ffcc80", "accent": "#ff9800",
        "grid": "rgba(80,40,10,0.5)", "profit_green": "#ffd740", "loss_red": "#ff6e40",
        "template": "plotly_dark", "candle_up": "#ffd740", "candle_down": "#ff6e40"
    }
}

if 'settings' not in st.session_state:
    st.session_state.settings = {
        'buy_threshold': 55.0, 'sell_threshold': 55.0,
        'sl_distance': 5.0, 'tp_distance': 10.0,
        'lot_size': 0.01, 'theme': 'Dark (Default)',
        'auto_refresh': True, 'refresh_interval': 15,
        'date_range': 'All Time'
    }

theme = THEMES[st.session_state.settings.get('theme', 'Dark (Default)')]
st.markdown(f"""<style>
    .stApp {{ background-color: {theme['bg']}; }}
    .stMetric {{ background-color: {theme['card_bg']}; border: 1px solid {theme['accent']}; border-radius: 12px; padding: 15px; }}
    .stMetric label {{ color: {theme['accent']} !important; font-weight: bold; font-size: 14px; }}
    .stMetric div {{ color: {theme['text']} !important; }}
    .trade-win {{ color: {theme['profit_green']}; font-weight: bold; }}
    .trade-loss {{ color: {theme['loss_red']}; font-weight: bold; }}
</style>""", unsafe_allow_html=True)

# ── Main dashboard (only shown after login) ─────────────────────
st.title("🛰️ APEX Institutional Omni-Terminal")

# CSV Upload in sidebar
st.sidebar.header(f"👤 {st.session_state.user_id}")
uploaded_file = st.sidebar.file_uploader("📤 Upload Trade History (CSV)", type="csv")
if uploaded_file and st.sidebar.button("Import CSV"):
    if append_csv_to_db(uploaded_file, user_db_path):
        st.sidebar.success("Data imported!")
        st.cache_data.clear()

df = load_user_data(user_db_path)
if df.empty:
    st.info("No data yet. Upload a CSV file with your trade history to get started.")
    st.stop()

comp = df[df['outcome'] != -1].copy()

# Top Metrics
m1, m2, m3, m4, m5 = st.columns(5)
win_rate = (len(comp[comp['outcome']==1])/max(1,len(comp))*100) if not comp.empty else 0.0
m1.metric("Win Rate", f"{win_rate:.1f}%")
m2.metric("P&L", f"${comp['profit'].sum():.2f}")
m3.metric("Trades", f"{len(comp)}")
m4.metric("Signals", f"{len(df)}")
m5.metric("VIX", f"{df['vix_level'].iloc[-1]:.2f}" if 'vix_level' in df.columns else "N/A")

# Equity Curve & Hourly Profit
col_a, col_b = st.columns(2)
if not comp.empty:
    comp_sorted = comp.sort_values('timestamp')
    comp_sorted['Cumulative Profit'] = comp_sorted['profit'].cumsum()
    fig_eq = px.area(comp_sorted, x='timestamp', y='Cumulative Profit', title="Equity Curve", color_discrete_sequence=[theme['profit_green']])
    fig_eq.update_layout(template=theme['template'])
    col_a.plotly_chart(fig_eq, use_container_width=True, key="equity")

    comp['Hour'] = comp['timestamp'].dt.hour
    hour_prof = comp.groupby('Hour')['profit'].sum().reset_index()
    fig_hour = px.bar(hour_prof, x='Hour', y='profit', title="Profit by Hour", color='profit', color_continuous_scale="RdYlGn")
    fig_hour.update_layout(template=theme['template'])
    col_b.plotly_chart(fig_hour, use_container_width=True, key="hourly")

st.markdown("---")
st.subheader("📊 BUY vs SELL")
if not comp.empty:
    buy_t = comp[comp['type']=='BUY']; sell_t = comp[comp['type']=='SELL']
    buy_wr = (buy_t['outcome'].sum()/max(1,len(buy_t))*100) if not buy_t.empty else 0
    sell_wr = (sell_t['outcome'].sum()/max(1,len(sell_t))*100) if not sell_t.empty else 0
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("BUY WR", f"{buy_wr:.1f}%", f"{len(buy_t)} trades")
    c2.metric("SELL WR", f"{sell_wr:.1f}%", f"{len(sell_t)} trades")
    c3.metric("BUY P&L", f"${buy_t['profit'].sum():.0f}")
    c4.metric("SELL P&L", f"${sell_t['profit'].sum():.0f}")

# ── Footer actions ─────────────────────────────────────────────
st.sidebar.markdown("---")
if st.sidebar.button("📥 Export Trade History (CSV)"):
    csv = comp.to_csv(index=False).encode()
    st.sidebar.download_button("Download", csv, "trade_history.csv")
