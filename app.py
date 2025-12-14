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
        # Ensure text columns are strings to prevent errors
        df['Status'] = df['Status'].astype(str)
        df['Staff_Name'] = df['Staff_Name'].astype(str)
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
    
    if df.empty:
        st.error("No data found. Please check your CSV file.")
    else:
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
            statuses = sub_df['Status'].values
            if 'VACANCY' in statuses: return 'VACANCY'
            if 'Transferred' in statuses: return 'Risk (Transfer)'
            return 'OK'
            
        # Group by Unit/Desk and unstack
        if not df.empty:
            heatmap_data = df.groupby(['Unit', 'Desk']).apply(get_aggregated_status).unstack()
            
            # FIX: Fill missing values (NaN) with "OK" to prevent crashes
            heatmap_data = heatmap_data.fillna("OK")
            
            # Sort Desks logic
            desired_order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                          'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            # Only index rows that actually exist in the data
            existing_order = [d for d in desired_order if d in heatmap_data.index]
            # Append any others that might exist but aren't in the list
            remaining = [d for d in heatmap_data.index if d not in desired_order]
            heatmap_data = heatmap_data.reindex(existing_order + remaining)
            
            # Color Map
            def color_map(val):
                val = str(val) # Safety check: convert to string
                if val == 'VACANCY': return 'background-color: #ef4444; color: white; font-weight: bold; text-align: center'
                if 'Risk' in val: return 'background-color: #f97316; color: white; font-weight: bold; text-align: center'
                return 'background-color: #10b981; color: white; text-align: center'
                
            st.dataframe(heatmap_data.style.map(color_map), use_container_width=True)

        # ALERTS LIST
        st.markdown("---")
        st.subheader("🔔 Critical Alerts")
        alerts = df[df['Status'].isin(['VACANCY', 'Transferred'])].copy()
        
        if not alerts.empty:
            # Color code the rows for the alert table
            def highlight_alerts(row):
                if row['Status'] == 'VACANCY':
                    return ['background-color: #fee2e2; color: #991b1b'] * len(row)
                if row['Status'] == 'Transferred':
                    return ['background-color: #ffedd5; color: #9a3412'] * len(row)
                return [''] * len(row)

            st.dataframe(
                alerts[['Unit', 'Desk', 'Staff_Name', 'Status', 'Action_Required']].style.apply(highlight_alerts, axis=1),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.success("No critical alerts found.")

# --- PAGE 2: SEARCH & GRAPHS ---
elif page == "Search & Graphs":
    st.title("📊 Detailed Staffing Analysis")
    
    if df.empty:
        st.warning("Data file is empty.")
    else:
        # SELECTION PANEL
        st.markdown("### Step 1: Select Area")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            # Sort units naturally
            units_sorted = sorted(df['Unit'].unique().astype(str))
            sel_unit = st.selectbox("Select Unit", units_sorted)
        with c2:
            # Filter Desks available for this unit
            available_desks = sorted(df[df['Unit'] == sel_unit]['Desk'].unique().astype(str))
            sel_desk = st.selectbox("Select Desk", available_desks)
        with c3:
            st.write("") # Spacer
            st.write("") # Spacer
            # Use session state to remember if button was clicked
            if 'show_data' not in st.session_state: st.session_state.show_data = False
            
            if st.button("Show Staff Details", type="primary", use_container_width=True):
                st.session_state.show_data = True
            
        if st.session_state.show_data:
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
                    
                    # Plotly Pie Chart
                    fig = px.pie(counts, values='Count', names='Status', 
                                 color='Status',
                                 color_discrete_map={'VACANCY':'#ef4444', 'Transferred':'#f97316', 'Active':'#10b981'},
                                 hole=0.4)
                    fig.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No data found for this selection.")
                    
            with gc2:
                st.markdown(f"### Staff List: {sel_unit} - {sel_desk}")
                
                if not subset.empty:
                    def highlight_rows(row):
                        if row['Status'] == 'VACANCY':
                            return ['background-color: #fee2e2; color: #991b1b'] * len(row)
                        if row['Status'] == 'Transferred':
                            return ['background-color: #ffedd5; color: #9a3412'] * len(row)
                        return [''] * len(row)

                    st.dataframe(
                        subset[['Staff_Name', 'Status', 'Action_Required']].style.apply(highlight_rows, axis=1),
                        use_container_width=True,
                        height=300,
                        hide_index=True
                    )
                else:
                    st.info("No staff entries found for this desk.")

# --- PAGE 3: ADMIN UPDATE ---
elif page == "Admin Update":
    st.title("🛠️ Admin Tools")
    
    pwd = st.text_input("Enter Admin Password", type="password")
    if pwd == "admin123":
        st.success("Access Granted")
        
        st.markdown("#### Add / Edit Staff Entry")
        
        ac1, ac2 = st.columns(2)
        with ac1:
            u_in = st.selectbox("Unit", df['Unit'].unique() if not df.empty else ["Unit 6"])
            d_in = st.selectbox("Desk", df['Desk'].unique() if not df.empty else ["PCR In-Charge"])
        with ac2:
            name_in = st.text_input("Staff Name (or 'VACANT POSITION')")
            status_in = st.selectbox("Status", ["Active", "Transferred", "VACANCY"])
            
        if st.button("Add / Update Entry"):
            new_row = {
                "Unit": u_in, "Desk": d_in, "Staff_Name": name_in,
                "Status": status_in, "Action_Required": "Immediate Deployment" if status_in == "VACANCY" else "", 
                "Original_Line": name_in
            }
            # Append
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_data(df)
            st.success("Record Added! Go to Dashboard to see changes.")
