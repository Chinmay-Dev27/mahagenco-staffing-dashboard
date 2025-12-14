import streamlit as st
import pandas as pd
import plotly.express as px
from github import Github # pip install PyGithub
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Staffing Portal", layout="wide", initial_sidebar_state="collapsed")
DATA_FILE = 'stitched_staffing_data.csv'
# UPDATE THIS with your actual repo name
REPO_NAME = "your-username/mahagenco-staffing-dashboard" 

# --- 1. GITHUB SYNC FUNCTION ---
def update_github(df):
    """Push updates to GitHub automatically"""
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DATA_FILE)
        csv_content = df.to_csv(index=False)
        repo.update_file(contents.path, "Admin Dashboard Update", csv_content, contents.sha)
        return True
    except Exception as e:
        st.error(f"GitHub Sync Error: {e}")
        return False

# --- 2. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_FILE)
        df['Status'] = df['Status'].astype(str)
        df['Staff_Name'] = df['Staff_Name'].astype(str)
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_local(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

df = load_data()

# --- 3. UI HEADER ---
st.title("🏭 Mahagenco Staffing Portal")
st.markdown("---")

# --- 4. NEW NAVIGATION (TABS) ---
# This replaces the hidden sidebar with clear tabs at the top
tab_home, tab_search, tab_admin = st.tabs(["📊 Dashboard Overview", "🔍 Search & Reports", "🛠️ Admin Tools"])

# ==========================================
# TAB 1: DASHBOARD OVERVIEW
# ==========================================
with tab_home:
    if df.empty:
        st.warning("⚠️ No data loaded. Please check GitHub or Admin tools.")
    else:
        # TOP METRICS ROW
        c1, c2, c3, c4 = st.columns(4)
        vac_count = len(df[df['Status'] == 'VACANCY'])
        risk_count = len(df[df['Status'] == 'Transferred'])
        active_count = len(df[df['Status'] == 'Active'])
        total_pos = len(df)
        
        c1.metric("🚨 Critical Vacancies", vac_count, delta="Immediate Action", delta_color="inverse")
        c2.metric("⚠️ Transfer Risks", risk_count, delta="Verify", delta_color="inverse")
        c3.metric("✅ Active Staff", active_count)
        c4.metric("📋 Total Positions", total_pos)
        
        st.write("") # Spacer
        
        # HEATMAP SECTION
        st.subheader("1. Plant Operational Map")
        st.caption("A high-level view of all units. Click 'Search & Reports' for details.")
        
        def get_aggregated_status(sub_df):
            statuses = sub_df['Status'].values
            if 'VACANCY' in statuses: return 'VACANCY'
            if 'Transferred' in statuses: return 'Risk (Transfer)'
            return 'OK'
            
        if not df.empty:
            heatmap_data = df.groupby(['Unit', 'Desk']).apply(get_aggregated_status).unstack()
            heatmap_data = heatmap_data.fillna("OK")
            
            # Smart Sorting
            order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                     'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            existing = [d for d in order if d in heatmap_data.index]
            remaining = [d for d in heatmap_data.index if d not in order]
            heatmap_data = heatmap_data.reindex(existing + remaining)
            
            # Styling
            def color_map(val):
                val = str(val)
                if val == 'VACANCY': return 'background-color: #ef4444; color: white; font-weight: bold; text-align: center; border: 1px solid white'
                if 'Risk' in val: return 'background-color: #f97316; color: white; font-weight: bold; text-align: center; border: 1px solid white'
                return 'background-color: #10b981; color: white; text-align: center; border: 1px solid white'
                
            st.dataframe(heatmap_data.style.map(color_map), use_container_width=True)

        # ALERTS TABLE
        st.write("")
        col_alert_1, col_alert_2 = st.columns([2, 1])
        with col_alert_1:
            st.subheader("🔔 Critical Action List")
            alerts = df[df['Status'].isin(['VACANCY', 'Transferred'])].copy()
            if not alerts.empty:
                def highlight(row):
                    if row['Status'] == 'VACANCY': return ['background-color: #fee2e2; color: #991b1b'] * len(row)
                    return ['background-color: #ffedd5; color: #9a3412'] * len(row)

                st.dataframe(
                    alerts[['Unit', 'Desk', 'Staff_Name', 'Status', 'Action_Required']].style.apply(highlight, axis=1),
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.success("🎉 No critical staffing issues found.")
        
        with col_alert_2:
             # Quick Graph
             if not df.empty:
                st.write("**Staffing Health**")
                counts = df['Status'].value_counts().reset_index()
                counts.columns = ['Status', 'Count']
                fig = px.pie(counts, values='Count', names='Status', 
                             color='Status',
                             color_discrete_map={'VACANCY':'#ef4444', 'Transferred':'#f97316', 'Active':'#10b981'},
                             hole=0.6)
                fig.update_layout(showlegend=False, height=250, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)


# ==========================================
# TAB 2: SEARCH & REPORTS
# ==========================================
with tab_search:
    st.header("🔍 Unit & Desk Analysis")
    
    # Filter Container
    with st.container():
        st.markdown("#### Select Area to View")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            u_sort = sorted(df['Unit'].unique().astype(str)) if not df.empty else []
            sel_unit = st.selectbox("Select Unit", u_sort)
        with c2:
            d_sort = sorted(df[df['Unit'] == sel_unit]['Desk'].unique().astype(str)) if not df.empty else []
            sel_desk = st.selectbox("Select Desk", d_sort)
        with c3:
            st.write("") 
            st.write("") 
            # BIG PRIMARY BUTTON
            # Using Session State to toggle view
            if 'search_active' not in st.session_state: st.session_state.search_active = False
            if st.button("Generate Report", type="primary", use_container_width=True):
                st.session_state.search_active = True

    st.markdown("---")

    # Results Area
    if st.session_state.search_active:
        subset = df[(df['Unit'] == sel_unit) & (df['Desk'] == sel_desk)]
        
        if subset.empty:
            st.info("No records found for this selection.")
        else:
            gc1, gc2 = st.columns([1, 2])
            
            with gc1:
                st.markdown(f"#### Status Distribution")
                counts = subset['Status'].value_counts().reset_index()
                counts.columns = ['Status', 'Count']
                fig = px.bar(counts, x='Status', y='Count', color='Status',
                             color_discrete_map={'VACANCY':'#ef4444', 'Transferred':'#f97316', 'Active':'#10b981'})
                fig.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
            
            with gc2:
                st.markdown(f"#### 👥 Staff Roster: {sel_unit} - {sel_desk}")
                
                def highlight_roster(row):
                    if row['Status'] == 'VACANCY': return ['background-color: #fee2e2; color: #991b1b; font-weight: bold'] * len(row)
                    if row['Status'] == 'Transferred': return ['background-color: #ffedd5; color: #9a3412; font-weight: bold'] * len(row)
                    return [''] * len(row)

                st.dataframe(
                    subset[['Staff_Name', 'Status', 'Action_Required']].style.apply(highlight_roster, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    height=300
                )

# ==========================================
# TAB 3: ADMIN TOOLS
# ==========================================
with tab_admin:
    col_center, _ = st.columns([1, 2])
    with col_center:
        st.header("🛠️ Admin Access")
        pwd = st.text_input("Enter Password to Edit Data", type="password")
    
    if pwd == "admin123":
        st.success("🔓 Access Granted")
        st.info("💡 Instructions: Select a Unit and Desk. You will see the current list of staff. Select a person (or Vacancy) to modify their status.")
        
        st.markdown("### 1. Select Position")
        ac1, ac2 = st.columns(2)
        with ac1:
            u_in = st.selectbox("Unit", df['Unit'].unique(), key='u_admin')
        with ac2:
            d_in = st.selectbox("Desk", df[df['Unit'] == u_in]['Desk'].unique(), key='d_admin')
            
        # Get Current Rows
        current_rows = df[(df['Unit'] == u_in) & (df['Desk'] == d_in)]
        
        if not current_rows.empty:
            st.markdown("### 2. Choose Person to Edit")
            # Build Options Map
            options = {}
            for idx, row in current_rows.iterrows():
                icon = "🟢"
                if row['Status'] == 'VACANCY': icon = "🔴"
                elif row['Status'] == 'Transferred': icon = "🟠"
                
                label = f"{icon} {row['Staff_Name']}  [{row['Status']}]"
                options[label] = idx
            
            selected_label = st.radio("Current Roster:", list(options.keys()))
            selected_index = options[selected_label]
            
            st.markdown("---")
            st.markdown("### 3. Update Details")
            
            ec1, ec2 = st.columns(2)
            with ec1:
                current_val = df.loc[selected_index, 'Staff_Name']
                # Auto-clear functional names for easier typing
                if "VACANT" in current_val or "Transferred" in current_val:
                    current_val = ""
                new_name = st.text_input("Staff Name (or 'VACANT POSITION')", value=current_val)
                
            with ec2:
                new_status = st.selectbox("New Status", ["Active", "Transferred", "VACANCY"])
            
            # BIG ACTION BUTTON
            st.write("")
            if st.button("💾 Update & Sync to GitHub", type="primary", use_container_width=True):
                with st.spinner("Processing Update..."):
                    # Update Local DF
                    if new_status == "VACANCY":
                        df.at[selected_index, 'Staff_Name'] = "VACANT POSITION"
                        df.at[selected_index, 'Status'] = "VACANCY"
                        df.at[selected_index, 'Action_Required'] = "Immediate Deployment"
                    elif new_status == "Transferred":
                        df.at[selected_index, 'Staff_Name'] = f"{new_name} (Transferred)"
                        df.at[selected_index, 'Status'] = "Transferred"
                        df.at[selected_index, 'Action_Required'] = "Verify Replacement"
                    else:
                        df.at[selected_index, 'Staff_Name'] = new_name
                        df.at[selected_index, 'Status'] = "Active"
                        df.at[selected_index, 'Action_Required'] = ""
                    
                    save_local(df)
                    
                    # Sync
                    if update_github(df):
                        st.success(f"✅ Successfully updated {u_in} - {d_in}!")
                        st.rerun()
        else:
            st.warning("No staff data found for this desk.")
