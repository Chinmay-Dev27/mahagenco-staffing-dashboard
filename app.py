import streamlit as st
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Staffing", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# --- 1. LOAD & PREPARE DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_FILE)
        df['Staff_Details'] = df['Staff_Details'].fillna("No Data").astype(str)
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_data(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

# --- 2. AUTHENTICATION ---
def check_password():
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    
    if not st.session_state['authenticated']:
        st.sidebar.markdown("### 🔐 Admin Access")
        pwd = st.sidebar.text_input("Password", type="password")
        if pwd == "admin123":
            st.session_state['authenticated'] = True
            st.rerun()
        return False
    return True

# --- 3. POPUP DIALOG ---
@st.dialog("📋 Position Details")
def show_details(unit, desk, status, details):
    st.markdown(f"### {unit} | {desk}")
    
    if status == "VACANCY":
        st.error(f"🚨 STATUS: {status}")
        st.markdown("**Action Required:** Immediate Deployment")
    elif "Risk" in status:
        st.warning(f"⚠️ STATUS: {status}")
        st.markdown("**Action Required:** Verify Replacement")
    else:
        st.success(f"✅ STATUS: {status}")
        
    st.markdown("---")
    st.markdown("#### 👥 Staff List:")
    # Clean up the details text for display
    clean_details = details.replace("|", "\n\n📌 **Note:**")
    st.info(clean_details)

# --- 4. MAIN APP ---
st.title("🏭 Plant Manpower Dashboard")
st.caption("Select any row in the table below to view staff details.")

df = load_data()

if not df.empty:
    # --- PREPARE TABLE DISPLAY ---
    # We want a nice table with Status Colors
    
    def color_status(val):
        """Colors the Status column based on value"""
        if val == 'VACANCY':
            return 'background-color: #fca5a5; color: #7f1d1d; font-weight: bold' # Red
        elif 'Risk' in val:
            return 'background-color: #fdba74; color: #9a3412; font-weight: bold' # Orange
        elif 'OK' in val:
            return 'background-color: #86efac; color: #14532d; font-weight: bold' # Green
        return ''

    # Reorder columns for clarity
    display_df = df[['Unit', 'Desk', 'Status', 'Staff_Details']].copy()
    
    # Sort by Status priority (VACANCY first)
    display_df['sort_key'] = display_df['Status'].map({'VACANCY': 0, 'Risk (Transfer)': 1, 'OK': 2})
    display_df = display_df.sort_values(['sort_key', 'Unit', 'Desk']).drop(columns=['sort_key'])

    # --- INTERACTIVE TABLE ---
    # Use on_select to capture clicks
    event = st.dataframe(
        display_df.style.applymap(color_status, subset=['Status']),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=600
    )

    # --- HANDLE SELECTION ---
    if len(event.selection.rows) > 0:
        selected_index = event.selection.rows[0]
        # Get the actual data row
        row_data = display_df.iloc[selected_index]
        
        show_details(
            row_data['Unit'],
            row_data['Desk'],
            row_data['Status'],
            row_data['Staff_Details']
        )

# --- 5. ADMIN SECTION ---
st.markdown("---")
with st.expander("🛠️ Update Staffing Data (Admin Only)"):
    if check_password():
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            u_in = st.selectbox("Unit", df['Unit'].unique())
            d_in = st.selectbox("Desk", df['Desk'].unique())
        with c2:
            s_in = st.selectbox("New Status", ["OK", "VACANCY", "Risk (Transfer)"])
        with c3:
            n_in = st.text_input("Staff Names / Notes")
            
        if st.button("Save Changes", type="primary"):
            mask = (df['Unit'] == u_in) & (df['Desk'] == d_in)
            if mask.any():
                df.loc[mask, 'Status'] = s_in
                df.loc[mask, 'Staff_Details'] = n_in
                save_data(df)
                st.success("✅ Saved!")
                st.rerun()
            else:
                st.error("Error: Could not find this Unit/Desk combination.")
