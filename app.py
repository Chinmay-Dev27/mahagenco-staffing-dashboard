import streamlit as st
import pandas as pd
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
        background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em; display: inline-block; margin-bottom: 2px;
    }
    .badge-transfer {
        background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em; display: inline-block; margin-bottom: 2px;
    }
    .badge-active {
        background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.9em; display: inline-block; margin-bottom: 2px;
    }
</style>
""", unsafe_allow_html=True)

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
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_local(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/8/82/Mahagenco_Logo.png/220px-Mahagenco_Logo.png", width=100)
    st.title("Parli TPS Ops")
    
    st.markdown("### 🔍 Global Search")
    search_term = st.text_input("Find Staff Member", placeholder="Enter name...")
    if search_term and not df.empty:
        res = df[df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            st.success(f"Found {len(res)} matches:")
            for _, r in res.iterrows():
                st.markdown(f"**{r['Staff_Name']}**\n\n*{r['Unit']} - {r['Desk']}*")
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

# ADDED SEARCH TAB BACK
tab_home, tab_search, tab_admin = st.tabs(["📊 Overview & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

# ==========================================
# TAB 1: OVERVIEW & ROSTER
# ==========================================
with tab_home:
    if df.empty:
        st.warning("⚠️ No data loaded.")
    else:
        # --- METRICS ROW ---
        op_df = df[df['Desk'] != 'Shift In-Charge']
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🚨 Critical Vacancies", len(op_df[op_df['Status'] == 'VACANCY']), delta_color="inverse")
        c2.metric("🟠 Transfers/Risks", len(op_df[op_df['Status'] == 'Transferred']), delta_color="inverse")
        c3.metric("✅ Active Staff", len(op_df[op_df['Status'] == 'Active']))
        c4.metric("👥 Total Positions", len(op_df))
        
        st.divider()

        # --- SHIFT IN CHARGE (HEADER) ---
        st.markdown("### 👨‍✈️ Shift In-Charge (EE)")
        ee_data = df[df['Desk'] == 'Shift In-Charge']
        if not ee_data.empty:
            ee_names = ee_data['Staff_Name'].unique()
            # Clean 'EE' from display name
            clean_ee_names = [re.sub(r'\s*EE\b', '', name, flags=re.IGNORECASE).strip() for name in ee_names]
            
            cols = st.columns(len(clean_ee_names))
            for i, name in enumerate(clean_ee_names):
                cols[i].info(f"**{name}**")
        else:
            st.info("No Shift In-Charge data found.")

        # --- TRANSPOSED MASTER TABLE ---
        st.subheader("🏭 Unit Status Map")
        
        def agg_staff(x):
            staff_list = []
            for _, row in x.iterrows():
                raw_name = row['Staff_Name']
                # IMPROVED CLEANING: Regex to remove (Transferred), (Trf), etc case-insensitive
                display_name = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', raw_name, flags=re.IGNORECASE).strip()

                if row['Status'] == 'VACANCY': 
                    staff_list.append(f'<div class="badge-vacant">🔴 VACANT</div>')
                elif row['Status'] == 'Transferred':
                    staff_list.append(f'<div class="badge-transfer">🟠 {display_name}</div>')
                else:
                    staff_list.append(f'<div class="badge-active">👤 {display_name}</div>')
            
            return "".join(staff_list)

        desks_order = [
            'PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
            'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)'
        ]
        
        units = sorted(op_df['Unit'].unique())
        table_data = []

        for desk in desks_order:
            row_data = {"Desk": f"<b>{desk}</b>"}
            for unit in units:
                matches = op_df[(op_df['Unit'] == unit) & (op_df['Desk'] == desk)]
                if matches.empty:
                    row_data[unit] = "-"
                else:
                    row_data[unit] = agg_staff(matches)
            table_data.append(row_data)
        
        display_df = pd.DataFrame(table_data)
        st.write(display_df.to_html(escape=False, index=False, classes="table table-bordered table-striped"), unsafe_allow_html=True)

# ==========================================
# TAB 2: SEARCH & REPORTS (RESTORED)
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
            st.markdown(f"#### 👥 Staff Roster: {sel_unit} - {sel_desk}")
            
            # Use same display logic (badges) for consistency
            for _, row in subset.iterrows():
                raw_name = row['Staff_Name']
                clean_name = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', raw_name, flags=re.IGNORECASE).strip()
                
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
        pwd = st.text_input("Enter Password", type="password")

    if pwd == "admin123":
        st.success("Access Granted")
        
        action_type = st.radio("Choose Action:", 
            ["🔄 Transfer Staff (Desk to Desk)", "✏️ Change Status (Mark Transferred/Active)", "➕ Add New Staff"], 
            horizontal=True
        )
        st.divider()

        # --- OPTION 1: CHANGE STATUS ---
        if action_type == "✏️ Change Status (Mark Transferred/Active)":
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
                        df.at[idx, 'Action_Required'] = "Immediate Deployment"
                    
                    save_local(df)
                    if update_github(df):
                        st.success(f"Updated {target_staff} to {new_status}")
                        st.rerun()

        # --- OPTION 2: PHYSICAL TRANSFER ---
        elif action_type == "🔄 Transfer Staff (Desk to Desk)":
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("1. Who?")
                u1 = st.selectbox("From Unit", df['Unit'].unique(), key="u1")
                d1 = st.selectbox("From Desk", df[df['Unit'] == u1]['Desk'].unique(), key="d1")
                people = df[(df['Unit'] == u1) & (df['Desk'] == d1) & (df['Staff_Name'] != 'VACANT POSITION')]['Staff_Name'].unique()
                if len(people) > 0:
                    p1 = st.selectbox("Person", people)
                else:
                    p1 = None
                    st.error("No staff here.")
                
            with col2:
                st.subheader("2. Where?")
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
                    df.at[src_idx, 'Action_Required'] = "Immediate Deployment"
                
                save_local(df)
                if update_github(df):
                    st.success("Transfer Successful!")
                    st.rerun()

        # --- OPTION 3: ADD NEW STAFF ---
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
