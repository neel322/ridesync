import streamlit as st
import pandas as pd
import math
import time
import requests
import polyline
import folium
from streamlit_folium import st_folium
from datetime import datetime
import sqlite3

# Page configuration
st.set_page_config(page_title="RideSync", page_icon="🚗", layout="wide")

# DATABASE SETUP (Replaces In-Memory Lists)
DB_NAME = 'ridesync.db'

def init_db():
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS rides (
            id INTEGER PRIMARY KEY, username TEXT, source TEXT, destination TEXT, 
            vehicle TEXT, ride_type TEXT, price REAL, status TEXT, timestamp REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_requests (
            id INTEGER PRIMARY KEY, passenger TEXT, pickup TEXT, destination TEXT, 
            vehicle TEXT, price REAL, status TEXT, driver TEXT, 
            expiry_time REAL, ride_type TEXT, current_passengers INTEGER, max_passengers INTEGER)''')
        conn.commit()

init_db()

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
    }
    .ride-card {
        background: #f0fdf4;
        border: 2px solid #22c55e;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        color: black !important;
    }
    .ride-card p, .ride-card h3, .ride-card h4, .ride-card strong {
        color: black !important;
    }
    .login-container {
        max-width: 500px;
        margin: auto;
        padding: 20px;
    }
    .stButton button { height: auto; padding-top: 15px; padding-bottom: 15px; }
    
    div[data-testid="stHorizontalBlock"] div[style*="background"] p,
    div[data-testid="stHorizontalBlock"] div[style*="background"] h4,
    div[data-testid="stHorizontalBlock"] div[style*="background"] strong {
        color: black !important;
    }
    
    .ride-request-card {
        background: #f0f9ff;
        border: 2px solid #3b82f6;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 15px;
        color: black !important;
    }
    .ride-request-card p, .ride-request-card h4, .ride-request-card strong {
        color: black !important;
    }
    
    .active-ride-card {
        background: #fffbeb;
        border: 2px solid #f59e0b;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        color: black !important;
    }
    .active-ride-card p, .active-ride-card h3, .active-ride-card strong {
        color: black !important;
    }
    
    .history-table {
        margin-top: 20px;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- 1. DATA & COORDINATES ---
LOCATIONS = {
    "LJU Campus": (22.9912, 72.4884),
    "Prahlad Nagar": (23.0120, 72.5108),
    "Anand Nagar": (23.0180, 72.5200),
    "Satellite": (23.0300, 72.5170),
    "Vastrapur": (23.0387, 72.5307),
    "Bodakdev": (23.0380, 72.5100),
    "Ambawadi": (23.0230, 72.5560),
    "Navrangpura": (23.0365, 72.5610)
}

# --- RIDE HISTORY MANAGEMENT ---
class RideHistoryManager:
    """Manages ride history using SQLite to support multi-tab."""
    def add_ride_for_user(self, username, ride_data):
        with sqlite3.connect(DB_NAME) as conn:
            # Logic to keep only last 20 rides
            c = conn.cursor()
            c.execute("SELECT id FROM rides WHERE username = ? ORDER BY timestamp ASC", (username,))
            rows = c.fetchall()
            if len(rows) >= 20:
                c.execute("DELETE FROM rides WHERE id = ?", (rows[0][0],))
            
            # Insert new ride
            timestamp = ride_data.get('timestamp', time.time())
            ride_type = 'Shared' if ride_data.get('sharing') else 'Solo'
            c.execute("INSERT INTO rides (username, source, destination, vehicle, ride_type, price, status, timestamp) VALUES (?,?,?,?,?,?,?,?)",
                      (username, ride_data.get('from'), ride_data.get('to'), ride_data.get('vehicle'), ride_type, ride_data.get('price'), 'Completed', timestamp))
            conn.commit()
    
    def get_user_dataframe(self, username):
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query("SELECT * FROM rides WHERE username = ? ORDER BY timestamp DESC", conn, params=(username,))
        
        if df.empty: return pd.DataFrame()
        
        data = []
        for _, row in df.iterrows():
            data.append({
                'Date & Time': datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'From': row['source'], 'To': row['destination'], 'Vehicle': row['vehicle'].title(),
                'Type': row['ride_type'], 'Price (₹)': row['price'], 'Status': row['status']
            })
        return pd.DataFrame(data)
    
    def get_user_stats(self, username):
        with sqlite3.connect(DB_NAME) as conn:
            res = conn.execute("SELECT COUNT(*), SUM(price) FROM rides WHERE username = ?", (username,)).fetchone()
        count = res[0] or 0
        total = res[1] or 0
        return {'total_rides': count, 'total_spent': total, 'avg_cost': (total/count if count else 0)}

if 'ride_history_manager' not in st.session_state:
    st.session_state.ride_history_manager = RideHistoryManager()

# Session State Initialization
if 'user' not in st.session_state: st.session_state.user = None
if 'ride_type' not in st.session_state: st.session_state.ride_type = 'solo'
if 'driver_mode' not in st.session_state: st.session_state.driver_mode = False
if 'driver_vehicle' not in st.session_state: st.session_state.driver_vehicle = None
if 'show_history' not in st.session_state: st.session_state.show_history = False
if 'ignored_requests' not in st.session_state: st.session_state.ignored_requests = set()

# --- DUMMY DATA INJECTION ---
def inject_dummy_data():
    if 'dummy_data_initialized' not in st.session_state:
        with sqlite3.connect(DB_NAME) as conn:
            # Users
            try: conn.execute("INSERT INTO users VALUES ('d1', '123')")
            except: pass
            try: conn.execute("INSERT INTO users VALUES ('p1', '123')")
            except: pass
            
            # History
            now = time.time()
            if conn.execute("SELECT COUNT(*) FROM rides WHERE username='d1'").fetchone()[0] == 0:
                conn.execute("INSERT INTO rides (username, source, destination, vehicle, ride_type, price, status, timestamp) VALUES (?,?,?,?,?,?,?,?)",
                             ('d1', 'LJU Campus', 'Prahlad Nagar', 'car', 'Solo', 250, 'Completed', datetime(2025, 12, 5).timestamp()))
            
            if conn.execute("SELECT COUNT(*) FROM rides WHERE username='p1'").fetchone()[0] == 0:
                conn.execute("INSERT INTO rides (username, source, destination, vehicle, ride_type, price, status, timestamp) VALUES (?,?,?,?,?,?,?,?)",
                             ('p1', 'Prahlad Nagar', 'LJU Campus', 'auto', 'Shared', 150, 'Completed', datetime(2025, 12, 2).timestamp()))
            conn.commit()
        st.session_state.dummy_data_initialized = True

inject_dummy_data()

# --- 2. HELPER FUNCTIONS ---

@st.cache_data
def get_route(src_name, dst_name):
    if src_name == dst_name: return 0, []
    src_lat, src_lon = LOCATIONS[src_name]
    dst_lat, dst_lon = LOCATIONS[dst_name]
    
    url = f"http://router.project-osrm.org/route/v1/driving/{src_lon},{src_lat};{dst_lon},{dst_lat}?overview=full"
    try:
        r = requests.get(url)
        data = r.json()
        if data["code"] == "Ok":
            route = data["routes"][0]
            dist_km = round(route["distance"] / 1000, 2)
            decoded_path = polyline.decode(route["geometry"])
            return dist_km, decoded_path
    except: pass
    
    dist = math.sqrt((dst_lat - src_lat)**2 + (dst_lon - src_lon)**2) * 111 * 1.2
    return round(dist, 2), [[src_lat, src_lon], [dst_lat, dst_lon]]

def display_map(src_name, dst_name, path_coords):
    src_lat, src_lon = LOCATIONS[src_name]
    dst_lat, dst_lon = LOCATIONS[dst_name]
    center_lat, center_lon = (src_lat + dst_lat) / 2, (src_lon + dst_lon) / 2
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    if path_coords: folium.PolyLine(path_coords, color="blue", weight=5, opacity=0.7).add_to(m)
    folium.Marker([src_lat, src_lon], popup="Pickup", tooltip=src_name, icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker([dst_lat, dst_lon], popup="Drop", tooltip=dst_name, icon=folium.Icon(color="red", icon="stop")).add_to(m)
    return m

def calculate_price(distance, vehicle_type, sharing):
    params = {'bike': {'fixed': 15, 'rate': 8}, 'auto': {'fixed': 25, 'rate': 12}, 'car': {'fixed': 45, 'rate': 18}}
    p = params[vehicle_type]
    raw_price = p['fixed'] + (distance * p['rate'])
    if vehicle_type == 'car':
        auto_price = params['auto']['fixed'] + (distance * params['auto']['rate'])
        if raw_price < (auto_price + 15): raw_price = auto_price + 15
    return round(raw_price * 0.8 if sharing else raw_price)

class RequestManager:
    """Handles real-time request syncing via SQLite"""
    def __init__(self, db_name=DB_NAME): self.db_name = db_name

    def create_request(self, data):
        with sqlite3.connect(self.db_name) as conn:
            r_type = 'Shared' if data.get('sharing') else 'Solo'
            max_p = 3 if data['vehicle'] == 'auto' else 4 if data['vehicle'] == 'car' else 1
            conn.execute('''
                INSERT INTO active_requests (passenger, pickup, destination, vehicle, price, status, driver, expiry_time, ride_type, current_passengers, max_passengers)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ''', (data['passenger'], data['pickup'], data['destination'], data['vehicle'], data['price'], 'pending', None, time.time() + 180, r_type, max_p))
            conn.commit()

    def get_pending_requests(self, vehicle_filter):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("""
                SELECT * FROM active_requests
                WHERE id IN (
                    SELECT MAX(id) FROM active_requests
                    WHERE status = 'pending'
                    AND vehicle = ?
                    AND expiry_time > ?
                    GROUP BY passenger
                )
                AND passenger NOT IN (
                    SELECT passenger FROM active_requests WHERE status = 'accepted'
                )
                ORDER BY id ASC
            """, (vehicle_filter, time.time())).fetchall()

    def get_driver_active_rides(self, driver_username):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM active_requests WHERE driver = ? AND status = 'accepted'", (driver_username,)).fetchall()

    def accept_request(self, req_id, driver_user):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("UPDATE active_requests SET status = 'accepted', driver = ? WHERE id = ?", (driver_user, req_id))
            conn.commit()

    def complete_request(self, req_id):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("UPDATE active_requests SET status = 'completed' WHERE id = ?", (req_id,))
            conn.commit()

    def get_passenger_active_request(self, passenger_user):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM active_requests WHERE passenger = ? AND status IN ('pending', 'accepted') ORDER BY id DESC LIMIT 1", (passenger_user,)).fetchone()

    def cancel_request(self, req_id):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("UPDATE active_requests SET status = 'cancelled' WHERE id = ?", (req_id,))
            conn.commit()

    def find_matching_rides(self, destination):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT * FROM active_requests 
                WHERE destination = ? 
                AND ride_type = 'Shared' 
                AND status IN ('pending', 'accepted')
                AND current_passengers < max_passengers
            """
            rows = conn.execute(query, (destination,)).fetchall()
            matches = []
            for r in rows:
                matches.append({
                    'id': r['id'], 'from': r['pickup'], 'to': r['destination'], 
                    'vehicle': r['vehicle'], 'price': r['price'], 
                    'current': r['current_passengers'], 'max': r['max_passengers'],
                    'driver': r['driver']
                })
            return matches

def cleanup_stale_requests():
    """
    Runs on every page load. Cleans up two types of ghost requests:
    1. Expired pending requests (past their 3-min window).
    2. Pending requests that belong to a passenger who already has an accepted ride
       (caused by double-clicks or rapid reruns creating duplicate rows).
    """
    with sqlite3.connect(DB_NAME) as conn:
        # Expire timed-out pending requests
        conn.execute(
            "UPDATE active_requests SET status = 'cancelled' WHERE status = 'pending' AND expiry_time <= ?",
            (time.time(),)
        )
        # Cancel older duplicate pending requests — keep only the MAX(id) per passenger
        conn.execute("""
            UPDATE active_requests SET status = 'cancelled'
            WHERE status = 'pending'
            AND id NOT IN (
                SELECT MAX(id) FROM active_requests
                WHERE status = 'pending'
                GROUP BY passenger
            )
        """)
        conn.commit()

cleanup_stale_requests()

if 'req_manager' not in st.session_state:
    st.session_state.req_manager = RequestManager()

# --- 3. SIDEBAR (ACCOUNT & DRIVER REGISTRATION) ---
with st.sidebar:
    if st.session_state.user:
        st.markdown("## 👤 Account")
        st.success(f"**{st.session_state.user['username']}**")
        
        # Show ride history stats in sidebar
        if st.session_state.user:
            username = st.session_state.user['username']
            stats = st.session_state.ride_history_manager.get_user_stats(username)
            
            st.markdown(f"**Total Rides:** {stats['total_rides']}")
            st.markdown(f"**Total Spent/Earned:** ₹{stats['total_spent']:.2f}")
        
        st.divider()
        
        # Driver Mode Toggle Logic
        st.markdown("## 🚗 Driver Mode")
        
        if not st.session_state.driver_mode:
            if st.button("🚕 Switch to Driver", use_container_width=True, key="switch_to_driver"):
                st.session_state.driver_mode = True
                st.rerun()
        else:
            st.info("**Driver Mode Active**")
            
            # Check for active driver ride from DB
            active_ride = None
            with sqlite3.connect(DB_NAME) as conn:
                conn.row_factory = sqlite3.Row
                active_ride = conn.execute("SELECT * FROM active_requests WHERE driver = ? AND status = 'accepted'", (st.session_state.user['username'],)).fetchone()

            # Vehicle Selection (only if no active ride)
            if not active_ride:
                if st.session_state.driver_vehicle:
                    st.markdown(f"**Current Vehicle:** {st.session_state.driver_vehicle.title()}")
                    if st.button("🔄 Change Vehicle", use_container_width=True, key="change_vehicle"):
                        st.session_state.driver_vehicle = None
                        st.rerun()
                else:
                    st.markdown("### Select Your Vehicle")
                    vehicle_choice = st.selectbox("Choose vehicle type:", ["bike", "auto", "car"], key="vehicle_select")
                    if st.button("Confirm Vehicle", use_container_width=True, key="confirm_vehicle"):
                        st.session_state.driver_vehicle = vehicle_choice
                        st.success(f"Vehicle set: {vehicle_choice.title()}")
                        st.rerun()
            else:
                st.markdown(f"**Current Vehicle:** {st.session_state.driver_vehicle.title()}")
                st.warning("⚠️ Cannot change vehicle during an active ride")
                
            if not active_ride:
                if st.button("👤 Switch to Passenger", use_container_width=True, key="switch_to_passenger"):
                    st.session_state.driver_mode = False
                    st.rerun()
        
        st.divider()
        
        if st.button("🚪 Logout", use_container_width=True, key="logout_button"):
            st.session_state.user = None
            st.session_state.driver_mode = False
            st.session_state.driver_vehicle = None
            st.session_state.show_history = False
            st.rerun()

# --- 4. APP LOGIC ---

if not st.session_state.user:
    # === LOGIN / SIGNUP SCREEN ===
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)
    st.markdown("""
    <div class="main-header">
        <h1>🚗 RideSync</h1>
        <p>Login to Book Your Ride</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["🔐 Login", "✍️ Sign Up"])
        
        with tab1:
            u = st.text_input("Username", key="login_user")
            p = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login", use_container_width=True, key="login_button"):
                with sqlite3.connect(DB_NAME) as conn:
                    res = conn.execute("SELECT password FROM users WHERE username = ?", (u,)).fetchone()
                    if res and res[0] == p:
                        st.session_state.user = {'username': u, 'balance': 500}
                        st.success("Login successful!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
        
        with tab2:
            nu = st.text_input("Choose Username", key="s_user")
            np = st.text_input("Choose Password", type="password", key="s_pass")
            if st.button("Sign Up", use_container_width=True, key="signup_button"):
                if nu and np:
                    try:
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("INSERT INTO users VALUES (?, ?)", (nu, np))
                            conn.commit()
                        st.success("Account created! Please login.")
                        st.rerun()
                    except:
                        st.error("Username already taken!")
                else: 
                    st.error("Please fill all fields")
    st.markdown("</div>", unsafe_allow_html=True)

else:
    # === DASHBOARD (After Login) ===
    st.markdown("""
    <div class="main-header">
        <h1>🚗 RideSync Dashboard</h1>
        <p>Smart Ride Sharing for LJU Campus</p>
    </div>
    """, unsafe_allow_html=True)
    
    # History toggle button
    col1, col2 = st.columns([3, 1])
    with col2:
        history_button_label = "📊 Hide History" if st.session_state.show_history else "📊 Show History"
        if st.button(history_button_label, use_container_width=True, key="toggle_history"):
            st.session_state.show_history = not st.session_state.show_history
            st.rerun()
    
    # 🚖 DRIVER VIEW SECTION
    if st.session_state.driver_mode and st.session_state.driver_vehicle:
        st.markdown("### 🚕 Driver Dashboard")
        
        # 1. GET ACTIVE RIDES FROM DB
        driver_active_rides = []
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            driver_active_rides = conn.execute("SELECT * FROM active_requests WHERE driver = ? AND status = 'accepted'", (st.session_state.user['username'],)).fetchall()

        # Display Active Rides
        for ride in driver_active_rides:
            st.markdown(f"""
            <div class="active-ride-card">
                <h3>🚗 Currently Driving ({ride['ride_type']})</h3>
                <p><strong>👤 Passenger:</strong> {ride['passenger']}</p>
                <p><strong>📍 Route:</strong> {ride['pickup']} → {ride['destination']}</p>
                <p><strong>🚗 Vehicle:</strong> {ride['vehicle'].title()}</p>
                <p><strong>💰 Earning:</strong> ₹{ride['price']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Button to complete the active ride
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(f"✅ Complete Ride for {ride['passenger']}", use_container_width=True, type="primary", key=f"d_comp_{ride['id']}"):
                    st.session_state.user['balance'] = st.session_state.user.get('balance', 500) + ride['price']
                    
                    # Update Passenger History
                    st.session_state.ride_history_manager.add_ride_for_user(
                        ride['passenger'],
                        {'from': ride['pickup'], 'to': ride['destination'], 'vehicle': ride['vehicle'], 'price': ride['price'], 'sharing': ride['ride_type']=='Shared'}
                    )
                    # Update Driver History
                    st.session_state.ride_history_manager.add_ride_for_user(
                        st.session_state.user['username'],
                        {'from': ride['pickup'], 'to': ride['destination'], 'vehicle': ride['vehicle'], 'price': ride['price'], 'sharing': ride['ride_type']=='Shared'}
                    )
                    
                    # Mark completed in DB
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE active_requests SET status = 'completed' WHERE id = ?", (ride['id'],))
                        conn.commit()
                    
                    st.success(f"Ride completed! ₹{ride['price']} added.")
                    st.rerun()
            st.divider()

        # 2. FIXED: If driver has an active ride, STOP HERE.
        #    Do NOT render the incoming requests section at all.
        if len(driver_active_rides) > 0:
            # Still auto-refresh so "Complete Ride" stays live
            time.sleep(1)
            st.rerun()

        # Only reached when driver has NO active rides
        st.markdown("### 📋 Incoming Requests")
        reqs = st.session_state.req_manager.get_pending_requests(st.session_state.driver_vehicle)

        # Filter out ignored requests
        final_reqs = [r for r in reqs if r['id'] not in st.session_state.ignored_requests]

        if not final_reqs:
            st.info("No available requests.")

        for req in final_reqs:
            rem = int(req['expiry_time'] - time.time())
            st.markdown(f"""<div class="ride-request-card"><h4>Request ({req['ride_type']}): {req['passenger']}</h4><p>{req['pickup']} ➝ {req['destination']} | ₹{req['price']}</p><p>Expires: {rem // 60}:{rem % 60:02d}</p></div>""", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("✅ Accept", key=f"a_{req['id']}", use_container_width=True):
                st.session_state.req_manager.accept_request(req['id'], st.session_state.user['username'])
                st.rerun()
            if c2.button("❌ Ignore", key=f"d_{req['id']}", use_container_width=True):
                st.session_state.ignored_requests.add(req['id'])
                st.rerun()

        # AUTO REFRESH (1 Second)
        time.sleep(1)
        st.rerun()

        # 3. DRIVER HISTORY & GRAPH
        if st.session_state.show_history:
            st.markdown("### 📊 Your Driving History")
            username = st.session_state.user['username']
            driver_history_df = st.session_state.ride_history_manager.get_user_dataframe(username)
            
            if not driver_history_df.empty:
                st.markdown("<div class='history-table'>", unsafe_allow_html=True)
                st.dataframe(driver_history_df, use_container_width=True, hide_index=True)
                
                st.subheader("📈 Monthly Income Overview")
                df_graph = driver_history_df.copy()
                df_graph['Date'] = pd.to_datetime(df_graph['Date & Time'])
                df_graph['Month'] = df_graph['Date'].dt.strftime('%b %Y')
                monthly_income = df_graph.groupby('Month')['Price (₹)'].sum()
                st.bar_chart(monthly_income)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Rides Driven", len(driver_history_df))
                with col2:
                    total_earned = driver_history_df['Price (₹)'].sum()
                    st.metric("Total Earned", f"₹{total_earned}")
                
                csv = driver_history_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download History", csv, f"history_{username}.csv", "text/csv", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No driving history yet.")
        
    # 🚗 PASSENGER VIEW SECTION
    else:
        # 1. Active Booking Display
        my_active_booking = None
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            # Get latest request that is not completed or cancelled
            my_active_booking = conn.execute(
                "SELECT * FROM active_requests WHERE passenger = ? AND status IN ('pending', 'accepted') ORDER BY id DESC LIMIT 1", 
                (st.session_state.user['username'],)
            ).fetchone()

        if my_active_booking:
            status_display = "Waiting for driver..." if my_active_booking['status'] == 'pending' else f"Driver {my_active_booking['driver']} is on the way!"
            
            st.markdown(f"""
            <div class="ride-card">
                <h3>✅ Active Ride Confirmed ({my_active_booking['ride_type']})</h3>
                <p><strong>📍 Route:</strong> {my_active_booking['pickup']} → {my_active_booking['destination']}</p>
                <p><strong>🚗 Vehicle:</strong> {my_active_booking['vehicle'].title()} | 
                <strong>💰 Price:</strong> ₹{my_active_booking['price']}</p>
                <p><strong>⏱️ {status_display}</strong></p>
            </div>
            """, unsafe_allow_html=True)
            
            # Cancel Button (Only if pending)
            if my_active_booking['status'] == 'pending':
                if st.button("❌ Cancel Request", use_container_width=False, key="cancel_ride"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE active_requests SET status = 'cancelled' WHERE id = ?", (my_active_booking['id'],))
                        conn.commit()
                    st.success("Ride cancelled!")
                    st.rerun()
            
            st.divider()
            
            time.sleep(1)
            st.rerun()

        else:
            # 2. Book a Ride Form
            st.markdown("### 📍 Book a Ride")
            col1, col2 = st.columns(2)
            with col1: 
                pickup = st.selectbox("🟢 Pickup Location", list(LOCATIONS.keys()), index=0, key="pickup_select")
            with col2: 
                dest_opts = [l for l in LOCATIONS.keys() if l != pickup]
                destination = st.selectbox("🔴 Drop Location", ["Select..."] + dest_opts, key="destination_select")

            if destination and destination != "Select...":
                
                distance_km, path_coords = get_route(pickup, destination)
                m = display_map(pickup, destination, path_coords)
                st_data = st_folium(m, height=300, use_container_width=True)
                
                st.info(f"📏 **Driving Distance:** {distance_km} km")
                st.divider()

                st.subheader("🚗 Choose Preference")
                t1, t2 = st.columns(2)
                solo_btn = "primary" if st.session_state.ride_type == 'solo' else "secondary"
                share_btn = "primary" if st.session_state.ride_type == 'shared' else "secondary"
                
                if t1.button("🚗 Solo Ride\n\nFull Privacy", type=solo_btn, use_container_width=True, key="solo_ride_btn"):
                    st.session_state.ride_type = 'solo'; st.rerun()
                if t2.button("👥 Share Ride\n\nSave Money", type=share_btn, use_container_width=True, key="share_ride_btn"):
                    st.session_state.ride_type = 'shared'; st.rerun()

                sharing = (st.session_state.ride_type == 'shared')

                # Show Existing Shared Rides
                if sharing:
                    matches = st.session_state.req_manager.find_matching_rides(destination)
                    if matches:
                        st.write("#### 🤝 Join Existing Ride")
                        for idx, m in enumerate(matches):
                            with st.container():
                                c1, c2, c3 = st.columns([3, 2, 2])
                                with c1: st.markdown(f"<p><strong>{m['from']} ➡ {m['to']}</strong></p>", unsafe_allow_html=True)
                                with c2: st.markdown(f"<p>🚗 {m['vehicle'].title()}</p>", unsafe_allow_html=True)
                                with c3:
                                    if st.button(f"Join @ ₹{m['price']}", key=f"join_{m['id']}_{idx}"):
                                        with sqlite3.connect(DB_NAME) as conn:
                                            # Guard: don't insert if passenger already has an active request
                                            existing = conn.execute(
                                                "SELECT id FROM active_requests WHERE passenger = ? AND status IN ('pending', 'accepted')",
                                                (st.session_state.user['username'],)
                                            ).fetchone()
                                            if not existing:
                                                conn.execute('''INSERT INTO active_requests (passenger, pickup, destination, vehicle, price, status, driver, expiry_time, ride_type, current_passengers, max_passengers)
                                                                VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, 'Shared', 1, 4)''', 
                                                                (st.session_state.user['username'], pickup, destination, m['vehicle'], m['price'], time.time() + 180))
                                                conn.commit()
                                                st.success("Joined! Waiting for driver to confirm.")
                                            else:
                                                st.warning("You already have an active request!")
                                        st.rerun()
                        st.divider()

                st.subheader("🚕 Create New Ride")
                vehicles = ['auto', 'car'] if sharing else ['bike', 'auto', 'car']
                
                for idx, v in enumerate(vehicles):
                    price = calculate_price(distance_km, v, sharing)
                    if v == 'bike': icon, cap = "🏍️", 1
                    elif v == 'auto': icon, cap = "🛺", 3
                    else: icon, cap = "🚗", 4
                    
                    b1, b2 = st.columns([3, 1])
                    with b1:
                        lbl = f"**{icon} {v.title()}**" + (" (Shared)" if sharing else "")
                        st.markdown(lbl)
                        st.caption(f"Max {cap} seats")
                    with b2:
                        if st.button(f"₹{price}", key=f"book_{v}_{idx}", type="primary", use_container_width=True):
                            r_type = 'Shared' if sharing else 'Solo'
                            with sqlite3.connect(DB_NAME) as conn:
                                # Guard: don't insert if passenger already has an active request
                                existing = conn.execute(
                                    "SELECT id FROM active_requests WHERE passenger = ? AND status IN ('pending', 'accepted')",
                                    (st.session_state.user['username'],)
                                ).fetchone()
                                if not existing:
                                    conn.execute('''INSERT INTO active_requests (passenger, pickup, destination, vehicle, price, status, driver, expiry_time, ride_type, current_passengers, max_passengers)
                                                    VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?, 1, ?)''', 
                                                    (st.session_state.user['username'], pickup, destination, v, price, time.time() + 180, r_type, cap))
                                    conn.commit()
                                    st.success(f"Booked {v}! Waiting for driver to accept.")
                                else:
                                    st.warning("You already have an active request!")
                            st.rerun()
                    st.divider()
        
        # 3. Passenger Ride History
        if st.session_state.show_history:
            st.markdown("### 📊 Your Ride History")
            username = st.session_state.user['username']
            history_df = st.session_state.ride_history_manager.get_user_dataframe(username)
            
            if not history_df.empty:
                st.markdown("<div class='history-table'>", unsafe_allow_html=True)
                st.dataframe(history_df, use_container_width=True, hide_index=True)
                
                stats = st.session_state.ride_history_manager.get_user_stats(username)
                
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("Total Rides", stats['total_rides'])
                with col2: st.metric("Total Spent", f"₹{stats['total_spent']:.2f}")
                with col3: st.metric("Avg Cost per Ride", f"₹{stats['avg_cost']:.2f}")
                
                csv = history_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download History", csv, f"history_{username}.csv", "text/csv", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No ride history yet.")