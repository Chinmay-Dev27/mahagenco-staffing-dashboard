import streamlit as st
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Staffing", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_FILE)
        df['Staff_Details'] = df['Staff_Details'].fillna("").astype(str)
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
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔐 Admin Access")
        pwd = st.sidebar.text_input("Password", type="password")
        if pwd == "admin123":
            st.session_state['authenticated'] = True
            st.rerun()
        return False
    return True

# --- 3. MAIN APP ---
st.title("🏭 Plant Staffing Roster")

df = load_data()

if df.empty:
    st.error("No data found. Please upload the CSV file.")
else:
    # --- SIDEBAR FILTERS (The "See Whatever You Want" part) ---
    st.sidebar.header("🔍 Filter Data")
    
    # 1. Unit Filter
    all_units = sorted(df['Unit'].unique())
    selected_units = st.sidebar.multiselect("Select Unit(s)", all_units, default=all_units)
    
    # 2. Desk Filter
    all_desks = sorted(df['Desk'].unique())
    selected_desks = st.sidebar.multiselect("Select Desk(s)", all_desks, default=all_desks)
    
    # 3. Name Search
    search_query = st.sidebar.text_input("👤 Search by Staff Name")

    # --- APPLY FILTERS ---
    filtered_df = df.copy()
    
    # Filter by Unit
    if selected_units:
        filtered_df = filtered_df[filtered_df['Unit'].isin(selected_units)]
        
    # Filter by Desk
    if selected_desks:
        filtered_df = filtered_df[filtered_df['Desk'].isin(selected_desks)]
        
    # Filter by Search Text
    if search_query:
        # Search in Staff Details (Case insensitive)
        filtered_df = filtered_df[filtered_df['Staff_Details'].str.contains(search_query, case=False, na=False)]

    # --- DISPLAY METRICS ---
    # Show quick counts based on the filtered view
    c1, c2, c3 = st.columns(3)
    c1.metric("Positions Shown", len(filtered_df))
    vacancies = len(filtered_df[filtered_df['Status'] == 'VACANCY'])
    c2.metric("Vacancies", vacancies, delta_color="inverse")
    risks = len(filtered_df[filtered_df['Status'].str.contains('Risk')])
    c3.metric("Transfer Risks", risks, delta_color="inverse")

    # --- MAIN DATA TABLE ---
    st.markdown("### 📋 Staff Details List")
    
    def highlight_status(val):
        color = ''
        if val == 'VACANCY':
            color = 'background-color: #fca5a5; color: #7f1d1d; font-weight: bold' # Red
        elif 'Risk' in val:
            color = 'background-color: #fdba74; color: #9a3412; font-weight: bold' # Orange
        elif 'OK' in val:
            color = 'background-color: #86efac; color: #14532d' # Green
        return color

    st.dataframe(
        filtered_df.style.applymap(highlight_status, subset=['Status']),
        use_container_width=True,
        height=600,
        column_config={
            "Unit": st.column_config.TextColumn("Unit", width="small"),
            "Desk": st.column_config.TextColumn("Desk", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Staff_Details": st.column_config.TextColumn("Staff Names / Remarks", width="large"),
        }
    )

# --- 4. ADMIN SECTION ---
st.markdown("---")
with st.expander("🛠️ Admin Tools (Edit Data)"):
    if check_password():
        st.write("Update the master database below:")
        
        c1, c2 = st.columns(2)
        with c1:
            u_in = st.selectbox("Unit", df['Unit'].unique())
            d_in = st.selectbox("Desk", df['Desk'].unique())
        with c2:
            s_in = st.selectbox("Status", ["OK", "VACANCY", "Risk (Transfer)"])
            n_in = st.text_area("Staff Details")
            
        if st.button("Save Changes"):
            mask = (df['Unit'] == u_in) & (df['Desk'] == d_in)
            if mask.any():
                df.loc[mask, 'Status'] = s_in
                df.loc[mask, 'Staff_Details'] = n_in
                save_data(df)
                st.success("✅ Database Updated!")
                st.rerun()
            else:
                st.error("Error: Selection not found in database.")
