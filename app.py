import streamlit as st
import pandas as pd
import plotly.express as px
import re
from github import Github
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# ⚠️ UPDATE REPO
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card {
        background-color: #0E1117;
        border: 1px solid #30333F;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
    }
    .badge-vacant {
        background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;
    }
    .badge-transfer {
        background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;
    }
    .badge-active {
        background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.85em; display: inline-block; margin-bottom: 2px;
    }
    .legend-box {
        font-size: 0.9em; 
        margin-top: 10px; 
        padding: 10px; 
        background-color: #f0f2f6; 
        color: #000000;
        border-radius: 5px;
        border: 1px solid #ccc;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False

# --- GITHUB & DATA FUNCTIONS ---
def update_github(df):
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(DATA_FILE)
            csv_content = df.to_csv(index=False)
            repo.update_file(contents.path, "Admin Update", csv_content, contents.sha)
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
        if 'Action_Required' in df.columns:
            df['Action_Required'] = df['Action_Required'].replace({
                'Immediate Deployment': 'Manpower Shortage',
                'Need Replacement': 'Staffing Action Required'
            })
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_local(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

df = load_data()

# --- HELPER: FORMAT NAME & DESIGNATION ---
def format_staff_name(raw_name):
    """
    Cleans name and formats designation into parentheses ()
    Ex: 'P.S. PAL DY.EE' -> 'P.S. PAL (DY.EE)'
    """
    if "VACANT" in raw_name:
        return "VACANT"
    
    # 1. Remove status text like (Transferred)
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', raw_name, flags=re.IGNORECASE).strip()
    
    # 2. Identify Designation at end of string
    # Patterns: JE, AE, DY.EE, DyEE, ADD.EE, Add EE, EE, etc.
    # regex looks for space followed by designation at the end
    pattern = r'\s+(JE|AE|DY\.? ?EE|ADD\.? ?EE|AD\.? ?EE|EE)\b'
    
    match = re.search(pattern, clean, flags=re.IGNORECASE)
    if match:
        desg = match.group(1) # The designation found
        name_only = clean[:match.start()].strip() # The name part
        return f"{name_only} ({desg})"
    
    return clean

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/8/82/Mahagenco_Logo.png/220px-Mahagenco_Logo.png", width=100)
    st.title("Parli TPS Ops")
    
    st.markdown("### 🔍 Global Search")
    search_term = st.text_input("Find Staff Member", placeholder="Enter name (e.g., Pal, Patil)...")
    
    if search_term and not df.empty:
        # Search logic: partial match, case insensitive
        res = df[df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        
        if not res.empty:
            st.success(f"Found {len(res)} matches:")
            for _, r in res.iterrows():
                formatted = format_staff_name(r['Staff_Name'])
                st.markdown(f"""
                <div style="background-color: #262730; padding: 10px; border-radius: 5px; margin-bottom: 5px; border: 1px solid #444;">
                    <strong>{formatted}</strong><br>
                    <span style="color: #bbb; font-size: 0.9em;">{r['Unit']} • {r['Desk']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("No match found.")

    st.divider()
    if not df.empty:
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📥 Download Excel/CSV", data=csv_buffer, file_name="Parli_Staff.csv", mime="text/csv")

# --- MAIN APP ---
st.title("⚡ Operation Staff Dashboard")
st.markdown(f"**Units:** 6, 7 & 8 | **Last Updated:** {pd.Timestamp.now().strftime('%d-%b-%Y')}")

tab_home, tab_search, tab_admin = st.tabs(["📊 Overview & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

# ==========================================
# TAB 1: OVERVIEW & ROSTER
# ==========================================
with tab_home:
    if df.empty:
        st.warning("⚠️ No data loaded.")
    else:
        op_df = df[df['Desk'] != 'Shift In-Charge']

        # --- 1. CHARTS ---
        c_chart1, c_chart2, c_metrics = st.columns([1, 1.2, 1.3])

        with c_chart1:
            st.markdown("##### 📊 Staff Status")
            status_counts = op_df['Status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig1 = px.pie(status_counts, values='Count', names='Status', 
                          color='Status',
                          color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'},
                          hole=0.4)
            fig1.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.3), margin=dict(t=0, b=0, l=0, r=0), height=220)
            st.plotly_chart(fig1, use_container_width=True)

        with c_chart2:
            st.markdown("##### ⚠️ Gaps by Unit")
            gaps_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
            if not gaps_df.empty:
                gap_counts = gaps_df.groupby(['Unit', 'Status']).size().reset_index(name='Count')
                fig2 = px.bar(gap_counts, x='Unit', y='Count', color='Status',
                              color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421'},
                              text_auto=True)
                fig2.update_layout(xaxis_title=None, yaxis_title=None, showlegend=True, 
                                   legend=dict(orientation="h", yanchor="bottom", y=-0.3),
                                   margin=dict(t=10, b=10, l=0, r=0), height=220)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.success("No Manpower Gaps!")

        with c_metrics:
            st.markdown("##### Key Metrics")
            m1, m2 = st.columns(2)
            m1.metric("🚨 Shortage", len(op_df[op_df['Status'] == 'VACANCY']), delta_color="inverse")
            m2.metric("🟠 Transferred", len(op_df[op_df['Status'] == 'Transferred']), delta_color="inverse")
            st.metric("✅ Total Active Staff", len(op_df[op_df['Status'] == 'Active']))

        st.divider()

        # --- 2. SHIFT IN CHARGE ---
        st.markdown("### 👨‍✈️ Shift In-Charge (EE)")
        ee_data = df[df['Desk'] == 'Shift In-Charge']
        if not ee_data.empty:
            ee_names = ee_data['Staff_Name'].unique()
            clean_ee_names = [re.sub(r'\s*EE\b', '', name, flags=re.IGNORECASE).strip() for name in ee_names]
            cols = st.columns(len(clean_ee_names))
            for i, name in enumerate(clean_ee_names):
                cols[i].info(f"**{name}**")
        else:
            st.info("No Shift In-Charge data found.")

        # --- 3. MAIN TABLE ---
        st.subheader("🏭 Unit Status Map")
        
        def agg_staff_html(x):
            staff_list = []
            for _, row in x.iterrows():
                # USE HELPER FUNCTION HERE
                display_name = format_staff_name(row['Staff_Name'])

                if row['Status'] == 'VACANCY': 
                    staff_list.append(f'<div class="badge-vacant">🔴 VACANT</div>')
                elif row['Status'] == 'Transferred':
                    staff_list.append(f'<div class="badge-transfer">🟠 {display_name}</div>')
                else:
                    staff_list.append(f'<div class="badge-active">👤 {display_name}</div>')
            return "".join(staff_list)

        desks_order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                       'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
        
        units = sorted(op_df['Unit'].unique())
        table_data = []

        for desk in desks_order:
            row_data = {"Desk": f"<b>{desk}</b>"}
            for unit in units:
                matches = op_df[(op_df['Unit'] == unit) & (op_df['Desk'] == desk)]
                row_data[unit] = "-" if matches.empty else agg_staff_html(matches)
            table_data.append(row_data)
        
        st.write(pd.DataFrame(table_data).to_html(escape=False, index=False, classes="table table-bordered table-striped"), unsafe_allow_html=True)

        # --- LEGEND ---
        st.markdown("""
        <div class="legend-box">
            <strong>Legend:</strong>&nbsp;&nbsp;
            <span class="badge-vacant">🔴 RED</span> = Position is <strong>VACANT</strong> (Manpower Shortage).&nbsp;&nbsp;
            <span class="badge-transfer">🟠 ORANGE</span> = Staff marked as <strong>TRANSFERRED</strong> (Staffing Action Required).&nbsp;&nbsp;
            <span class="badge-active">🟢 GREEN</span> = Active / Deployed.
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()

        # --- DETAILED LISTS ---
        c_list1, c_list2 = st.columns(2)
        with c_list1:
            st.subheader("🚨 Manpower Shortage List")
            vac_list = op_df[op_df['Status'] == 'VACANCY'][['Unit', 'Desk', 'Action_Required']]
            if not vac_list.empty:
                st.dataframe(vac_list, use_container_width=True, hide_index=True)
            else:
                st.success("No active shortages.")

        with c_list2:
            st.subheader("🟠 Transferred Employees")
            trf_list = op_df[op_df['Status'] == 'Transferred'][['Unit', 'Desk', 'Staff_Name']]
            if not trf_list.empty:
                trf_list['Staff_Name'] = trf_list['Staff_Name'].apply(format_staff_name)
                st.dataframe(trf_list, use_container_width=True, hide_index=True)
            else:
                st.success("No transferred staff pending.")

# ==========================================
# TAB 2: SEARCH & REPORTS
# ==========================================
with tab_search:
    st.header("🔍 Unit & Desk Analysis")

    if not df.empty:
        c1, c2 = st.columns([1, 1])
        with c1:
            u_sort = sorted(df['Unit'].unique().astype(str))
            sel_unit = st.selectbox("Select Unit", u_sort)
        with c2:
            d_sort = sorted(df[df['Unit'] == sel_unit]['Desk'].unique().astype(str))
            sel_desk = st.selectbox("Select Desk (Operation Area)", d_sort)

        st.markdown("---")
        subset = df[(df['Unit'] == sel_unit) & (df['Desk'] == sel_desk)]
        
        if subset.empty:
            st.info("No records found.")
        else:
            col_search_chart, col_search_list = st.columns([1, 2])
            
            with col_search_chart:
                st.markdown("#### Status Breakdown")
                search_counts = subset['Status'].value_counts().reset_index()
                search_counts.columns = ['Status', 'Count']
                fig_search = px.pie(search_counts, values='Count', names='Status', 
                              color='Status',
                              color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'},
                              hole=0.4)
                fig_search.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2), margin=dict(t=0, b=0, l=0, r=0), height=200)
                st.plotly_chart(fig_search, use_container_width=True)

            with col_search_list:
                st.markdown(f"#### 👥 Staff Roster: {sel_unit} - {sel_desk}")
                for _, row in subset.iterrows():
                    # USE HELPER FUNCTION HERE
                    clean_name = format_staff_name(row['Staff_Name'])
                    
                    if row['Status'] == 'VACANCY':
                        st.error(f"🔴 **VACANT POSITION** (Action: {row['Action_Required']})")
                    elif row['Status'] == 'Transferred':
                        st.warning(f"🟠 **{clean_name}** - *Transferred*")
                    else:
                        st.success(f"👤 **{clean_name}** - *Active*")

# ==========================================
# TAB 3: ADMIN ACTIONS
# ==========================================
with tab_admin:
    col_center, _ = st.columns([1, 2])
    with col_center:
        st.header("🛠️ Admin Tools")
        
        if not st.session_state.admin_logged_in:
            pwd = st.text_input("Enter Admin Password", type="password")
            if st.button("Login"):
                if pwd == "admin123":
                    st.session_state.admin_logged_in = True
                    st.rerun()
                else:
                    st.error("Incorrect Password")
        else:
            c_logout_1, c_logout_2 = st.columns([3, 1])
            with c_logout_1:
                st.success("🔓 Logged in as Admin")
            with c_logout_2:
                if st.button("🚪 Logout"):
                    st.session_state.admin_logged_in = False
                    st.rerun()
            
            st.divider()

            action_type = st.radio("Choose Action:", 
                ["🔄 Transfer Staff (Desk to Desk)", "✏️ Change Status (Transferred/Vacancy)", "📝 Update Designation & Name", "➕ Add New Staff"], 
                horizontal=True
            )
            st.markdown("---")

            if action_type == "📝 Update Designation & Name":
                st.info("Update employee name and assign official designation.")
                c1, c2 = st.columns(2)
                unit_sel = c1.selectbox("Unit", df['Unit'].unique())
                desk_sel = c2.selectbox("Desk", df[df['Unit'] == unit_sel]['Desk'].unique())
                
                staff_rows = df[(df['Unit'] == unit_sel) & (df['Desk'] == desk_sel) & (df['Status'] != 'VACANCY')]
                if not staff_rows.empty:
                    target_staff = st.selectbox("Select Staff Member", staff_rows['Staff_Name'].unique())
                    idx = df[(df['Unit'] == unit_sel) & (df['Desk'] == desk_sel) & (df['Staff_Name'] == target_staff)].index[0]
                    current_full_name = df.at[idx, 'Staff_Name']
                    
                    ec1, ec2 = st.columns([2, 1])
                    new_name_input = ec1.text_input("Employee Name (Without Designation)", value=current_full_name)
                    designation_opts = ["-- Select --", "Junior Engineer (JE)", "Assistant Engineer (AE)", "Deputy Ex. Engineer (DyEE)", "Addl. Ex. Engineer (Add EE)", "Executive Engineer (EE)"]
                    new_desg = ec2.selectbox("Select Designation", designation_opts)
                    
                    if st.button("Update Details"):
                        if new_desg != "-- Select --":
                            desg_map = {
                                "Junior Engineer (JE)": "JE",
                                "Assistant Engineer (AE)": "AE",
                                "Deputy Ex. Engineer (DyEE)": "DyEE",
                                "Addl. Ex. Engineer (Add EE)": "Add EE",
                                "Executive Engineer (EE)": "EE"
                            }
                            suffix = desg_map[new_desg]
                            base_name = re.sub(r'\s+(JE|AE|DyEE|Add EE|EE|Add.EE|Ad.EE)\b', '', new_name_input, flags=re.IGNORECASE).strip()
                            final_name = f"{base_name} {suffix}"
                        else:
                            final_name = new_name_input
                        
                        df.at[idx, 'Staff_Name'] = final_name
                        save_local(df)
                        if update_github(df):
                            st.success(f"Updated to: {final_name}")
                            st.rerun()

            elif action_type == "✏️ Change Status (Transferred/Vacancy)":
                c1, c2 = st.columns(2)
                unit_sel = c1.selectbox("Unit", df['Unit'].unique())
                desk_sel = c2.selectbox("Desk", df[df['Unit'] == unit_sel]['Desk'].unique())
                staff_rows = df[(df['Unit'] == unit_sel) & (df['Desk'] == desk_sel)]
                if not staff_rows.empty:
                    target_staff = st.selectbox("Select Staff Member", staff_rows['Staff_Name'].unique())
                    idx = df[(df['Unit'] == unit_sel) & (df['Desk'] == desk_sel) & (df['Staff_Name'] == target_staff)].index[0]
                    new_status = st.selectbox("New Status", ["Active", "Transferred", "VACANCY", "Long Leave"])
                    
                    if st.button("Update Status"):
                        df.at[idx, 'Status'] = new_status
                        if new_status == "VACANCY":
                            df.at[idx, 'Staff_Name'] = "VACANT POSITION"
                            df.at[idx, 'Action_Required'] = "Manpower Shortage"
                        save_local(df)
                        if update_github(df):
                            st.success(f"Updated {target_staff} to {new_status}")
                            st.rerun()

            elif action_type == "🔄 Transfer Staff (Desk to Desk)":
                col1, col2 = st.columns(2)
                with col1:
                    u1 = st.selectbox("From Unit", df['Unit'].unique(), key="u1")
                    d1 = st.selectbox("From Desk", df[df['Unit'] == u1]['Desk'].unique(), key="d1")
                    people = df[(df['Unit'] == u1) & (df['Desk'] == d1) & (df['Staff_Name'] != 'VACANT POSITION')]['Staff_Name'].unique()
                    p1 = st.selectbox("Person", people) if len(people) > 0 else None
                with col2:
                    u2 = st.selectbox("To Unit", df['Unit'].unique(), key="u2")
                    d2 = st.selectbox("To Desk", df[df['Unit'] == u2]['Desk'].unique(), key="d2")
                old_seat_opt = st.radio("What happens to old seat?", ["Mark VACANT", "No Change (Swap)"], horizontal=True)

                if p1 and st.button("Execute Transfer"):
                    src_idx = df[(df['Unit'] == u1) & (df['Desk'] == d1) & (df['Staff_Name'] == p1)].index[0]
                    tgt_vac_rows = df[(df['Unit'] == u2) & (df['Desk'] == d2) & (df['Status'] == 'VACANCY')]
                    if not tgt_vac_rows.empty:
                        tgt_idx = tgt_vac_rows.index[0]
                        df.at[tgt_idx, 'Staff_Name'] = p1
                        df.at[tgt_idx, 'Status'] = "Active"
                        df.at[tgt_idx, 'Action_Required'] = ""
                    else:
                        new_row = {"Unit": u2, "Desk": d2, "Staff_Name": p1, "Status": "Active", "Action_Required": "", "Original_Line": ""}
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

                    if old_seat_opt == "Mark VACANT":
                        df.at[src_idx, 'Staff_Name'] = "VACANT POSITION"
                        df.at[src_idx, 'Status'] = "VACANCY"
                        df.at[src_idx, 'Action_Required'] = "Manpower Shortage"
                    
                    save_local(df)
                    if update_github(df):
                        st.success("Transfer Successful!")
                        st.rerun()

            elif action_type == "➕ Add New Staff":
                c1, c2, c3 = st.columns(3)
                new_u = c1.selectbox("Unit", df['Unit'].unique())
                new_d = c2.selectbox("Desk", df[df['Unit'] == new_u]['Desk'].unique())
                new_n = c3.text_input("Staff Name")
                if st.button("Add Person"):
                    vac_rows = df[(df['Unit'] == new_u) & (df['Desk'] == new_d) & (df['Status'] == 'VACANCY')]
                    if not vac_rows.empty:
                        idx = vac_rows.index[0]
                        df.at[idx, 'Staff_Name'] = new_n
                        df.at[idx, 'Status'] = "Active"
                        df.at[idx, 'Action_Required'] = ""
                    else:
                        new_row = {"Unit": new_u, "Desk": new_d, "Staff_Name": new_n, "Status": "Active", "Action_Required": "", "Original_Line": ""}
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_local(df)
                    if update_github(df):
                        st.success("Added Successfully")
                        st.rerun()
