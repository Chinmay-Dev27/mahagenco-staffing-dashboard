import streamlit as st
import pandas as pd
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Advanced Dashboard", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_FILE)
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_data(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

df = load_data()

# --- 2. SIDEBAR NAVIGATION ---
st.sidebar.title("🏭 Mahagenco")
page = st.sidebar.radio("Go to:", ["Dashboard Home", "Search & Graphs", "Admin Update"])

# --- PAGE 1: DASHBOARD HOME (Heatmap & Alerts) ---
if page == "Dashboard Home":
    st.title("🏭 Plant Status Overview")
    
    # METRICS
    col1, col2, col3 = st.columns(3)
    total_vacancies = len(df[df['Status'] == 'VACANCY'])
    total_transfers = len(df[df['Status'] == 'Transferred'])
    col1.metric("🚨 Total Vacancies", total_vacancies)
    col2.metric("⚠️ Total Transfers", total_transfers)
    col3.metric("✅ Total Active Staff", len(df[df['Status'] == 'Active']))
    
    st.markdown("---")
    
    # HEATMAP (Aggregated View)
    st.subheader("1. Operational Heatmap")
    st.caption("Red = Has Vacancy | Orange = Has Transfer Risk | Green = All Active")
    
    # Aggregate data to get 1 status per Unit/Desk
    def get_aggregated_status(sub_df):
        if 'VACANCY' in sub_df['Status'].values: return 'VACANCY'
        if 'Transferred' in sub_df['Status'].values: return 'Risk (Transfer)'
        return 'OK'
        
    heatmap_data = df.groupby(['Unit', 'Desk']).apply(get_aggregated_status).unstack()
    
    # Sort Desks
    desk_order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                  'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
    heatmap_data = heatmap_data.reindex(desk_order)
    
    # Color Map
    def color_map(val):
        if val == 'VACANCY': return 'background-color: #ef4444; color: white; font-weight: bold; text-align: center'
        if 'Risk' in val: return 'background-color: #f97316; color: white; font-weight: bold; text-align: center'
        return 'background-color: #10b981; color: white; text-align: center'
        
    st.dataframe(heatmap_data.style.applymap(color_map), use_container_width=True)

    # ALERTS LIST
    st.markdown("---")
    st.subheader("🔔 Critical Alerts")
    alerts = df[df['Status'].isin(['VACANCY', 'Transferred'])].copy()
    if not alerts.empty:
        st.dataframe(
            alerts[['Unit', 'Desk', 'Staff_Name', 'Status', 'Action_Required']],
            hide_index=True,
            use_container_width=True
        )
    else:
        st.success("No critical alerts found.")

# --- PAGE 2: SEARCH & GRAPHS ---
elif page == "Search & Graphs":
    st.title("📊 Detailed Staffing Analysis")
    
    # SELECTION PANEL
    st.markdown("### Step 1: Select Area")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        sel_unit = st.selectbox("Select Unit", df['Unit'].unique())
    with c2:
        # Filter Desks based on Unit? (Optional, but let's show all for now)
        sel_desk = st.selectbox("Select Desk", df['Desk'].unique())
    with c3:
        st.write("") # Spacer
        st.write("") # Spacer
        show_btn = st.button("Show Staff Details", type="primary", use_container_width=True)
        
    if show_btn:
        st.markdown("---")
        
        # Filter Data
        subset = df[(df['Unit'] == sel_unit) & (df['Desk'] == sel_desk)]
        
        # COLUMNS: GRAPH LEFT, TABLE RIGHT
        gc1, gc2 = st.columns([1, 2])
        
        with gc1:
            st.markdown("### Status Graph")
            if not subset.empty:
                # Count Statuses
                counts = subset['Status'].value_counts().reset_index()
                counts.columns = ['Status', 'Count']
                
                # Plotly Pie/Bar Chart
                fig = px.pie(counts, values='Count', names='Status', 
                             color='Status',
                             color_discrete_map={'VACANCY':'red', 'Transferred':'orange', 'Active':'green'},
                             hole=0.4)
                fig.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No data found.")
                
        with gc2:
            st.markdown(f"### Staff List: {sel_unit} - {sel_desk}")
            
            def highlight_rows(row):
                if row['Status'] == 'VACANCY':
                    return ['background-color: #fee2e2; color: #991b1b'] * len(row)
                if row['Status'] == 'Transferred':
                    return ['background-color: #ffedd5; color: #9a3412'] * len(row)
                return [''] * len(row)

            st.dataframe(
                subset[['Staff_Name', 'Status', 'Action_Required']].style.apply(highlight_rows, axis=1),
                use_container_width=True,
                height=300
            )

# --- PAGE 3: ADMIN UPDATE ---
elif page == "Admin Update":
    st.title("🛠️ Admin Tools")
    
    pwd = st.text_input("Enter Admin Password", type="password")
    if pwd == "admin123":
        st.success("Access Granted")
        
        st.markdown("#### Add / Edit Staff Entry")
        
        ac1, ac2 = st.columns(2)
        with ac1:
            u_in = st.selectbox("Unit", df['Unit'].unique())
            d_in = st.selectbox("Desk", df['Desk'].unique())
        with ac2:
            name_in = st.text_input("Staff Name (or 'VACANT POSITION')")
            status_in = st.selectbox("Status", ["Active", "Transferred", "VACANCY"])
            
        if st.button("Add / Update Entry"):
            new_row = {
                "Unit": u_in, "Desk": d_in, "Staff_Name": name_in,
                "Status": status_in, "Action_Required": "", "Original_Line": name_in
            }
            # Append
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_data(df)
            st.success("Record Added! Go to Dashboard to see changes.")
