import streamlit as st
import pandas as pd
import plotly.express as px
from github import Github # pip install PyGithub
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Staffing Portal", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")
DATA_FILE = 'stitched_staffing_data.csv'

# ⚠️ UPDATE REPO
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

# --- 1. GITHUB & DATA FUNCTIONS ---
def update_github(df):
    """Push updates to GitHub"""
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(DATA_FILE)
            csv_content = df.to_csv(index=False)
            repo.update_file(contents.path, "Admin Dashboard Update", csv_content, contents.sha)
        except:
            repo.create_file(DATA_FILE, "Initial Commit", df.to_csv(index=False))
        return True
    except Exception as e:
        st.error(f"GitHub Sync Error: {e}")
        return False

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

# --- 2. SIDEBAR ---
with st.sidebar:
    st.title("🏭 MAHAGENCO")
    st.markdown("### Parli TPS - Ops")
    
    if not df.empty:
        # Download Button
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Download Data (Excel/CSV)",
            data=csv_buffer.getvalue(),
            file_name="Parli_Staff_Dashboard.csv",
            mime="text/csv",
            use_container_width=True
        )

# --- 3. MAIN HEADER ---
st.title("Operation Staff Dashboard")
st.markdown(f"**Units:** 6, 7 & 8 | **Last Updated:** {pd.Timestamp.now().strftime('%d-%b-%Y')}")

# --- 4. NAVIGATION ---
tab_home, tab_search, tab_admin = st.tabs(["📊 Dashboard Overview", "🔍 Search & Reports", "🛠️ Admin Tools"])

# ==========================================
# TAB 1: DASHBOARD OVERVIEW
# ==========================================
with tab_home:
    if df.empty:
        st.warning("⚠️ No data loaded. Please check CSV file.")
    else:
        # --- LEADERSHIP SECTION ---
        st.subheader("👨‍✈️ Shift In-Charge (EE)")
        ee_data = df[df['Desk'] == 'Shift In-Charge']
        if not ee_data.empty:
            # Show distinct EEs (since they are common for U6/U7)
            distinct_ees = ee_data[['Staff_Name']].drop_duplicates()
            cols = st.columns(len(distinct_ees))
            for i, (_, row) in enumerate(distinct_ees.iterrows()):
                with cols[i % len(cols)]:
                    st.info(f"**{row['Staff_Name']}**")
        else:
            st.info("No Shift In-Charge data found.")

        st.divider()

        # --- TOP METRICS ---
        c1, c2, c3, c4 = st.columns(4)
        # Exclude Shift In-Charge from vacancy counts usually, but include if rows exist
        op_df = df[df['Desk'] != 'Shift In-Charge'] 
        
        vac_count = len(op_df[op_df['Status'] == 'VACANCY'])
        risk_count = len(op_df[op_df['Status'] == 'Transferred'])
        
        c1.metric("🚨 Critical Vacancies", vac_count, delta="Immediate Action", delta_color="inverse")
        c2.metric("⚠️ Transfer Risks", risk_count, delta="Verify", delta_color="inverse")
        c3.metric("✅ Active Staff", len(op_df[op_df['Status'] == 'Active']))
        c4.metric("📋 Total Positions", len(op_df))

        # --- HEATMAP ---
        st.subheader("🏭 Plant Operational Map")
        
        def get_aggregated_status(sub_df):
            statuses = sub_df['Status'].values
            if 'VACANCY' in statuses: return 'VACANCY'
            if 'Transferred' in statuses: return 'Risk (Transfer)'
            return 'OK'

        if not op_df.empty:
            heatmap_data = op_df.groupby(['Unit', 'Desk']).apply(get_aggregated_status).unstack()
            heatmap_data = heatmap_data.fillna("OK")

            # Custom Order
            order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                     'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            heatmap_data = heatmap_data.reindex(columns=[c for c in order if c in heatmap_data.columns])

            def color_map(val):
                val = str(val)
                if val == 'VACANCY': return 'background-color: #ef4444; color: white; font-weight: bold; text-align: center; border: 1px solid white'
                if 'Risk' in val: return 'background-color: #f97316; color: white; font-weight: bold; text-align: center; border: 1px solid white'
                return 'background-color: #10b981; color: white; text-align: center; border: 1px solid white'

            st.dataframe(heatmap_data.style.map(color_map), use_container_width=True)

        # --- ALERTS & DISTRIBUTION ---
        col_alert, col_chart = st.columns([2, 1])
        
        with col_alert:
            st.subheader("🔔 Critical Action List")
            alerts = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])].copy()
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
                st.success("No critical alerts.")

        with col_chart:
            st.subheader("📊 Status Split")
            counts = op_df['Status'].value_counts().reset_index()
            counts.columns = ['Status', 'Count']
            fig = px.pie(counts, values='Count', names='Status', 
                         color='Status',
                         color_discrete_map={'VACANCY':'#ef4444', 'Transferred':'#f97316', 'Active':'#10b981'},
                         hole=0.4)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250)
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# TAB 2: SEARCH & REPORTS
# ==========================================
with tab_search:
    st.header("🔍 Unit & Desk Analysis")

    with st.container():
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
            if 'search_active' not in st.session_state: st.session_state.search_active = False
            if st.button("Generate Report", type="primary", use_container_width=True):
                st.session_state.search_active = True

    st.markdown("---")

    if st.session_state.search_active:
        subset = df[(df['Unit'] == sel_unit) & (df['Desk'] == sel_desk)]
        
        if subset.empty:
            st.info("No records found.")
        else:
            st.markdown(f"#### 👥 Staff Roster: {sel_unit} - {sel_desk}")
            
            def highlight_roster(row):
                if row['Status'] == 'VACANCY': return ['background-color: #fee2e2; color: #991b1b; font-weight: bold'] * len(row)
                if row['Status'] == 'Transferred': return ['background-color: #ffedd5; color: #9a3412; font-weight: bold'] * len(row)
                return [''] * len(row)

            st.dataframe(
                subset[['Staff_Name', 'Status', 'Action_Required']].style.apply(highlight_roster, axis=1),
                use_container_width=True,
                hide_index=True
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

        admin_mode = st.radio("Select Action:", ["Simple Edit", "Transfer Staff (Wizard)"], horizontal=True)
        st.markdown("---")

        # --- MODE 1: SIMPLE EDIT ---
        if admin_mode == "Simple Edit":
            ac1, ac2 = st.columns(2)
            with ac1:
                u_in = st.selectbox("Unit", df['Unit'].unique(), key='u_simp')
            with ac2:
                d_in = st.selectbox("Desk", df[df['Unit'] == u_in]['Desk'].unique(), key='d_simp')

            current_rows = df[(df['Unit'] == u_in) & (df['Desk'] == d_in)]

            if not current_rows.empty:
                options = {}
                for idx, row in current_rows.iterrows():
                    icon = "🟢"
                    if row['Status'] == 'VACANCY': icon = "🔴"
                    elif row['Status'] == 'Transferred': icon = "🟠"
                    label = f"{icon} {row['Staff_Name']}  [{row['Status']}]"
                    options[label] = idx

                selected_label = st.radio("Select Person to Edit:", list(options.keys()))
                idx = options[selected_label]

                ec1, ec2 = st.columns(2)
                with ec1:
                    cur_name = df.loc[idx, 'Staff_Name']
                    if "VACANT" in cur_name: cur_name = ""
                    new_name = st.text_input("Name", value=cur_name)
                with ec2:
                    new_status = st.selectbox("Status", ["Active", "Transferred", "VACANCY"])

                if st.button("Update Record"):
                    df.at[idx, 'Staff_Name'] = new_name if new_status != "VACANCY" else "VACANT POSITION"
                    df.at[idx, 'Status'] = new_status
                    df.at[idx, 'Action_Required'] = "Immediate Deployment" if new_status == "VACANCY" else ""

                    save_local(df)
                    if update_github(df):
                        st.success("Updated Successfully!")
                        st.rerun()

        # --- MODE 2: TRANSFER WIZARD ---
        elif admin_mode == "Transfer Staff (Wizard)":
            st.markdown("#### 1. Select Staff to Transfer")
            c1, c2 = st.columns(2)
            with c1:
                src_unit = st.selectbox("From Unit", df['Unit'].unique(), key='src_u')
            with c2:
                src_desk = st.selectbox("From Desk", df[df['Unit'] == src_unit]['Desk'].unique(), key='src_d')

            src_rows = df[(df['Unit'] == src_unit) & (df['Desk'] == src_desk) & (df['Status'] != 'VACANCY')]

            if not src_rows.empty:
                src_opts = {f"{row['Staff_Name']}": idx for idx, row in src_rows.iterrows()}
                staff_name = st.selectbox("Select Person", list(src_opts.keys()))
                src_idx = src_opts[staff_name]

                st.markdown("#### 2. Destination")
                dc1, dc2 = st.columns(2)
                with dc1:
                    tgt_unit = st.selectbox("To Unit", df['Unit'].unique(), key='tgt_u')
                with dc2:
                    tgt_desk = st.selectbox("To Desk", df[df['Unit'] == tgt_unit]['Desk'].unique(), key='tgt_d')

                st.markdown("#### 3. Old Seat Action")
                old_seat_action = st.radio("Select Action for old position:", 
                                         ["Mark as VACANT", "Filled by Replacement"], horizontal=True)

                replacement_name = ""
                if old_seat_action == "Filled by Replacement":
                    replacement_name = st.text_input("Enter Replacement Name")

                if st.button("Confirm Transfer", type="primary"):
                    with st.spinner("Processing..."):
                        # 1. Update Old Seat
                        if old_seat_action == "Mark as VACANT":
                            df.at[src_idx, 'Staff_Name'] = "VACANT POSITION"
                            df.at[src_idx, 'Status'] = "VACANCY"
                            df.at[src_idx, 'Action_Required'] = "Immediate Deployment"
                        else:
                            df.at[src_idx, 'Staff_Name'] = replacement_name
                            df.at[src_idx, 'Status'] = "Active"
                            df.at[src_idx, 'Action_Required'] = ""

                        # 2. Update New Seat (Check vacancy)
                        tgt_vacancies = df[(df['Unit'] == tgt_unit) & (df['Desk'] == tgt_desk) & (df['Status'] == 'VACANCY')]

                        if not tgt_vacancies.empty:
                            fill_idx = tgt_vacancies.index[0]
                            df.at[fill_idx, 'Staff_Name'] = staff_name
                            df.at[fill_idx, 'Status'] = "Active"
                            df.at[fill_idx, 'Action_Required'] = ""
                        else:
                            # Append if no vacancy
                            new_row = {"Unit": tgt_unit, "Desk": tgt_desk, "Staff_Name": staff_name, "Status": "Active", "Action_Required": "", "Original_Line": staff_name}
                            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

                        save_local(df)
                        if update_github(df):
                            st.success("Transfer Complete!")
                            st.rerun()
