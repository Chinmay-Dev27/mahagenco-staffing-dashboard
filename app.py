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
        with st.sidebar.expander("🔐 Admin Login"):
            pwd = st.text_input("Password", type="password")
            if pwd == "admin123":
                st.session_state['authenticated'] = True
                st.rerun()
        return False
    return True

# --- 3. MAIN DASHBOARD ---
st.title("🏭 Plant Manpower Dashboard")

df = load_data()

if df.empty:
    st.error("No data found. Please upload the CSV file.")
else:
    # --- SECTION 1: HEATMAP OVERVIEW ---
    st.subheader("1. Operational Heatmap")
    st.caption("Overview of all Units and Desks. Red = Vacancy, Orange = Risk, Green = OK.")

    # Create a Pivot Table for the Heatmap
    # Map status to color codes for conditional formatting
    def color_map(val):
        if val == 'VACANCY': return 'background-color: #ef4444; color: white; font-weight: bold; text-align: center'
        if 'Risk' in val: return 'background-color: #f97316; color: white; font-weight: bold; text-align: center'
        return 'background-color: #10b981; color: white; text-align: center'

    pivot_df = df.pivot(index='Desk', columns='Unit', values='Status')
    
    # Sort Rows (Desks) in logical order
    desk_order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                  'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
    pivot_df = pivot_df.reindex(desk_order)

    # Display Heatmap Table
    st.dataframe(pivot_df.style.applymap(color_map), use_container_width=True)

    # --- SECTION 2: SEARCH & DETAILS ---
    st.markdown("---")
    st.subheader("2. Staff Details & Search")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.info("👇 **Filter the list:**")
        # Filters
        all_units = sorted(df['Unit'].unique())
        sel_unit = st.selectbox("Select Unit", ["All"] + all_units)
        
        all_desks = sorted(df['Desk'].unique())
        sel_desk = st.selectbox("Select Desk", ["All"] + all_desks)
        
        search_txt = st.text_input("🔍 Search by Name")

    # Apply Filters
    filtered_df = df.copy()
    if sel_unit != "All":
        filtered_df = filtered_df[filtered_df['Unit'] == sel_unit]
    if sel_desk != "All":
        filtered_df = filtered_df[filtered_df['Desk'] == sel_desk]
    if search_txt:
        filtered_df = filtered_df[filtered_df['Staff_Details'].str.contains(search_txt, case=False)]

    with col2:
        # Display Results
        st.write(f"Showing **{len(filtered_df)}** records:")
        
        def highlight_row(row):
            # Highlight the Status cell
            res = [''] * len(row)
            if row['Status'] == 'VACANCY':
                res[2] = 'background-color: #fca5a5; color: #7f1d1d; font-weight: bold'
            elif 'Risk' in row['Status']:
                res[2] = 'background-color: #fdba74; color: #9a3412; font-weight: bold'
            return res

        st.dataframe(
            filtered_df.style.apply(highlight_row, axis=1),
            use_container_width=True,
            height=400,
            column_config={
                "Staff_Details": st.column_config.TextColumn("Staff List / Remarks", width="large"),
                "Status": st.column_config.TextColumn("Current Status", width="small")
            }
        )

# --- 4. ADMIN SECTION ---
st.markdown("---")
if check_password():
    st.subheader("🛠️ Admin: Update Data")
    c1, c2, c3 = st.columns(3)
    with c1:
        u_in = st.selectbox("Unit", df['Unit'].unique(), key="u_adm")
    with c2:
        d_in = st.selectbox("Desk", df['Desk'].unique(), key="d_adm")
    with c3:
        s_in = st.selectbox("New Status", ["OK", "VACANCY", "Risk (Transfer)"], key="s_adm")
    
    n_in = st.text_area("Update Staff Details", key="n_adm")
    
    if st.button("Save Changes"):
        mask = (df['Unit'] == u_in) & (df['Desk'] == d_in)
        if mask.any():
            df.loc[mask, 'Status'] = s_in
            df.loc[mask, 'Staff_Details'] = n_in
            save_data(df)
            st.success("Updated!")
            st.rerun()
