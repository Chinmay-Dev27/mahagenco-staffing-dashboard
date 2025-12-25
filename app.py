import streamlit as st
import pandas as pd
import plotly.express as px
import re
from github import Github
from fpdf import FPDF
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #0E1117; border: 1px solid #30333F; border-radius: 10px; padding: 15px; text-align: center; }
    .badge-vacant { background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; }
    .badge-transfer { background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; }
    .badge-active { background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.85em; }
    .card-container { background-color: #262730; padding: 15px; border-radius: 8px; border: 1px solid #444; margin-bottom: 10px; }
    .card-header { font-weight: bold; font-size: 1.1em; color: #fff; border-bottom: 1px solid #555; padding-bottom: 5px; margin-bottom: 10px; }
    .stButton>button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'admin_logged_in' not in st.session_state: st.session_state.admin_logged_in = False

# --- PDF GENERATOR CLASS ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'MAHAGENCO Parli TPS - Operation Staff Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

# --- DATA FUNCTIONS ---
def update_github(df):
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(DATA_FILE)
            repo.update_file(contents.path, "Admin Update", df.to_csv(index=False), contents.sha)
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
                'Immediate Deployment': 'Manpower Shortage', 'Need Replacement': 'Staffing Action Required'
            })
        return df
    except: return pd.DataFrame()

def save_local(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

def format_staff_name(raw_name):
    if "VACANT" in raw_name: return "VACANT"
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', raw_name, flags=re.IGNORECASE).strip()
    pattern = r'\s+(JE|AE|DY\.? ?EE|ADD\.? ?EE|AD\.? ?EE|EE)\b'
    match = re.search(pattern, clean, flags=re.IGNORECASE)
    if match:
        return f"{clean[:match.start()].strip()} ({match.group(1)})"
    return clean

def generate_pdf_report(df):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Summary Metrics
    active = len(df[df['Status']=='Active'])
    vacant = len(df[df['Status']=='VACANCY'])
    pdf.cell(0, 10, f"Date: {pd.Timestamp.now().strftime('%d-%b-%Y')} | Active: {active} | Shortage: {vacant}", 0, 1)
    pdf.ln(5)
    
    # Table Header
    pdf.set_fill_color(200, 220, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(25, 8, "Unit", 1, 0, 'C', 1)
    pdf.cell(50, 8, "Desk", 1, 0, 'C', 1)
    pdf.cell(70, 8, "Staff Name", 1, 0, 'C', 1)
    pdf.cell(35, 8, "Status", 1, 1, 'C', 1)
    
    # Table Body
    pdf.set_font("Arial", size=9)
    for _, row in df.iterrows():
        name = format_staff_name(row['Staff_Name'])
        status = row['Status']
        
        # Color logic for PDF text (simplified)
        pdf.set_text_color(0, 0, 0)
        if status == 'VACANCY': pdf.set_text_color(220, 50, 50)
        elif status == 'Transferred': pdf.set_text_color(220, 150, 0)
            
        pdf.cell(25, 8, str(row['Unit']), 1, 0, 'C')
        pdf.cell(50, 8, str(row['Desk'])[:25], 1, 0, 'L')
        pdf.cell(70, 8, name[:35], 1, 0, 'L')
        pdf.cell(35, 8, status, 1, 1, 'C')
        pdf.set_text_color(0, 0, 0) # Reset
        
    return pdf.output(dest='S').encode('latin-1')

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/8/82/Mahagenco_Logo.png/220px-Mahagenco_Logo.png", width=100)
    st.title("Parli TPS Ops")
    
    st.markdown("### 🔍 Global Search")
    search_term = st.text_input("Find Staff Member", placeholder="e.g. Pal, Patil...")
    if search_term and not df.empty:
        res = df[df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            st.success(f"Found {len(res)} matches:")
            for _, r in res.iterrows():
                formatted = format_staff_name(r['Staff_Name'])
                st.markdown(f"<div style='border:1px solid #555; padding:8px; border-radius:5px; margin-bottom:5px;'><b>{formatted}</b><br><small>{r['Unit']} • {r['Desk']}</small></div>", unsafe_allow_html=True)
        else: st.warning("No match found.")

    st.divider()
    if not df.empty:
        # Excel Download
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📥 Download CSV", data=csv_buffer, file_name="Parli_Staff.csv", mime="text/csv")
        
        # PDF Download
        try:
            pdf_bytes = generate_pdf_report(df)
            st.download_button("📄 Download PDF Report", data=pdf_bytes, file_name="Shift_Report.pdf", mime="application/pdf")
        except Exception as e:
            st.error(f"PDF Error: {e}")

# --- MAIN APP ---
st.title("⚡ Operation Staff Dashboard")
st.markdown(f"**Units:** 6, 7 & 8 | **Last Updated:** {pd.Timestamp.now().strftime('%d-%b-%Y')}")

tab_home, tab_search, tab_admin = st.tabs(["📊 Overview & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

# ================= TAB 1: OVERVIEW =================
with tab_home:
    if df.empty: st.warning("No data loaded.")
    else:
        op_df = df[df['Desk'] != 'Shift In-Charge']
        c1, c2, c3 = st.columns([1, 1.5, 1.2])
        
        with c1:
            st.markdown("##### 📊 Status")
            fig1 = px.pie(op_df['Status'].value_counts().reset_index(), values='count', names='Status', 
                          color='Status', color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4)
            fig1.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=0,b=0), height=200)
            st.plotly_chart(fig1, use_container_width=True)

        with c2:
            st.markdown("##### ⚠️ Gaps by Unit")
            gaps_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
            if not gaps_df.empty:
                # GROUPED BAR CHART
                fig2 = px.histogram(gaps_df, x="Unit", color="Status", barmode="group",
                                    color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421'}, text_auto=True)
                fig2.update_layout(xaxis_title=None, yaxis_title=None, showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10,b=10), height=200)
                st.plotly_chart(fig2, use_container_width=True)
            else: st.success("No Manpower Gaps!")

        with c3:
            st.markdown("##### Key Metrics")
            m1, m2 = st.columns(2)
            m1.metric("🚨 Shortage", len(op_df[op_df['Status'] == 'VACANCY']), delta_color="inverse")
            m2.metric("🟠 Transferred", len(op_df[op_df['Status'] == 'Transferred']), delta_color="inverse")
            st.metric("✅ Total Active", len(op_df[op_df['Status'] == 'Active']))

        st.divider()
        st.markdown("### 👨‍✈️ Shift In-Charge (EE)")
        ee_rows = df[df['Desk'] == 'Shift In-Charge']['Staff_Name'].unique()
        cols = st.columns(len(ee_rows) if len(ee_rows)>0 else 1)
        for i, name in enumerate(ee_rows):
            clean_name = re.sub(r'\s*EE\b', '', name, flags=re.IGNORECASE).strip()
            cols[i].info(f"**{clean_name}**")

        st.divider()
        
        # --- MOBILE VIEW TOGGLE ---
        col_head, col_tog = st.columns([3, 1])
        with col_head: st.subheader("🏭 Unit Status Map")
        with col_tog: mobile_view = st.toggle("📱 Mobile Cards", value=False)

        if mobile_view:
            # CARD VIEW FOR MOBILE
            units = sorted(op_df['Unit'].unique())
            tabs = st.tabs(units)
            for i, unit in enumerate(units):
                with tabs[i]:
                    unit_data = op_df[op_df['Unit'] == unit]
                    for _, row in unit_data.iterrows():
                        name = format_staff_name(row['Staff_Name'])
                        color = "#00CC96" if row['Status']=="Active" else "#ff4b4b" if row['Status']=="VACANCY" else "#ffa421"
                        st.markdown(f"""
                        <div class="card-container" style="border-left: 5px solid {color};">
                            <div style="font-weight:bold; font-size:1.1em; color:white;">{row['Desk']}</div>
                            <div style="margin-top:5px; color:{color}; font-weight:500;">{name}</div>
                            <div style="font-size:0.8em; color:#aaa;">Status: {row['Status']}</div>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            # TABLE VIEW FOR DESKTOP
            def agg_staff_html(x):
                html = []
                for _, row in x.iterrows():
                    name = format_staff_name(row['Staff_Name'])
                    if row['Status'] == 'VACANCY': html.append(f'<div class="badge-vacant">🔴 VACANT</div>')
                    elif row['Status'] == 'Transferred': html.append(f'<div class="badge-transfer">🟠 {name}</div>')
                    else: html.append(f'<div class="badge-active">👤 {name}</div>')
                return "".join(html)

            desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            units = sorted(op_df['Unit'].unique())
            table_data = []
            for desk in desks:
                row = {"Desk": f"<b>{desk}</b>"}
                for unit in units:
                    match = op_df[(op_df['Unit']==unit) & (op_df['Desk']==desk)]
                    row[unit] = "-" if match.empty else agg_staff_html(match)
                table_data.append(row)
            st.write(pd.DataFrame(table_data).to_html(escape=False, index=False, classes="table table-bordered"), unsafe_allow_html=True)
            
            st.markdown("""
            <div style="margin-top:10px; padding:10px; background:#f0f2f6; color:black; border-radius:5px;">
                <strong>Legend:</strong>&nbsp;&nbsp;<span class="badge-vacant">🔴 RED</span> = VACANT (Shortage).&nbsp;&nbsp;
                <span class="badge-transfer">🟠 ORANGE</span> = TRANSFERRED (Action Required).&nbsp;&nbsp;<span class="badge-active">🟢 GREEN</span> = Active.
            </div>""", unsafe_allow_html=True)

        # Detailed Lists
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🚨 Shortages")
            st.dataframe(op_df[op_df['Status']=='VACANCY'][['Unit','Desk','Action_Required']], use_container_width=True, hide_index=True)
        with c2:
            st.subheader("🟠 Transfers")
            trf = op_df[op_df['Status']=='Transferred'][['Unit','Desk','Staff_Name']].copy()
            if not trf.empty: trf['Staff_Name'] = trf['Staff_Name'].apply(format_staff_name)
            st.dataframe(trf, use_container_width=True, hide_index=True)

# ================= TAB 2: SEARCH =================
with tab_search:
    st.header("🔍 Unit & Desk Analysis")
    if not df.empty:
        c1, c2 = st.columns(2)
        u_sel = c1.selectbox("Select Unit", sorted(df['Unit'].unique().astype(str)))
        d_sel = c2.selectbox("Select Desk", sorted(df[df['Unit']==u_sel]['Desk'].unique().astype(str)))
        st.markdown("---")
        subset = df[(df['Unit']==u_sel) & (df['Desk']==d_sel)]
        if subset.empty: st.info("No records.")
        else:
            c_ch, c_li = st.columns([1, 2])
            with c_ch:
                fig = px.pie(subset['Status'].value_counts().reset_index(), values='count', names='Status', color='Status',
                             color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4)
                fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=0,b=0), height=200)
                st.plotly_chart(fig, use_container_width=True)
            with c_li:
                st.markdown(f"#### Roster: {u_sel} - {d_sel}")
                for _, row in subset.iterrows():
                    name = format_staff_name(row['Staff_Name'])
                    if row['Status']=='VACANCY': st.error(f"🔴 **VACANT** ({row['Action_Required']})")
                    elif row['Status']=='Transferred': st.warning(f"🟠 **{name}** - Transferred")
                    else: st.success(f"👤 **{name}** - Active")

# ================= TAB 3: ADMIN =================
with tab_admin:
    st.header("🛠️ Admin Tools")
    if not st.session_state.admin_logged_in:
        if st.text_input("Password", type="password") == "admin123" and st.button("Login"):
            st.session_state.admin_logged_in = True
            st.rerun()
    else:
        if st.button("🚪 Logout"):
            st.session_state.admin_logged_in = False
            st.rerun()
        st.divider()
        
        act = st.radio("Action:", ["🔄 Transfer", "✏️ Change Status", "📝 Update Details", "➕ Add Staff"], horizontal=True)
        st.markdown("---")
        
        if act == "📝 Update Details":
            c1, c2 = st.columns(2)
            u = c1.selectbox("Unit", df['Unit'].unique())
            d = c2.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
            rows = df[(df['Unit']==u) & (df['Desk']==d) & (df['Status']!='VACANCY')]
            if not rows.empty:
                p = st.selectbox("Staff", rows['Staff_Name'].unique())
                idx = df[(df['Unit']==u) & (df['Desk']==d) & (df['Staff_Name']==p)].index[0]
                n_name = c1.text_input("Name", value=df.at[idx,'Staff_Name'])
                n_desg = c2.selectbox("Designation", ["-- Select --", "JE", "AE", "Dy.EE", "Add.EE", "EE"])
                if st.button("Update"):
                    final = f"{n_name} ({n_desg})" if n_desg != "-- Select --" else n_name
                    df.at[idx, 'Staff_Name'] = final
                    save_local(df); update_github(df); st.success("Updated!"); st.rerun()
        
        elif act == "✏️ Change Status":
            c1, c2 = st.columns(2)
            u = c1.selectbox("Unit", df['Unit'].unique())
            d = c2.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
            rows = df[(df['Unit']==u) & (df['Desk']==d)]
            if not rows.empty:
                p = st.selectbox("Staff", rows['Staff_Name'].unique())
                idx = df[(df['Unit']==u) & (df['Desk']==d) & (df['Staff_Name']==p)].index[0]
                stat = st.selectbox("New Status", ["Active", "Transferred", "VACANCY", "Long Leave"])
                if st.button("Update"):
                    df.at[idx, 'Status'] = stat
                    if stat == "VACANCY":
                        df.at[idx, 'Staff_Name'] = "VACANT POSITION"
                        df.at[idx, 'Action_Required'] = "Manpower Shortage"
                    save_local(df); update_github(df); st.success("Status Updated!"); st.rerun()

        elif act == "🔄 Transfer":
            c1, c2 = st.columns(2)
            u1 = c1.selectbox("From Unit", df['Unit'].unique())
            d1 = c1.selectbox("From Desk", df[df['Unit']==u1]['Desk'].unique())
            ppl = df[(df['Unit']==u1) & (df['Desk']==d1) & (df['Staff_Name']!='VACANT POSITION')]['Staff_Name'].unique()
            p = c1.selectbox("Person", ppl) if len(ppl)>0 else None
            
            u2 = c2.selectbox("To Unit", df['Unit'].unique())
            d2 = c2.selectbox("To Desk", df[df['Unit']==u2]['Desk'].unique())
            old_act = st.radio("Old Seat:", ["Mark VACANT", "No Change"], horizontal=True)
            
            if p and st.button("Transfer"):
                src = df[(df['Unit']==u1) & (df['Desk']==d1) & (df['Staff_Name']==p)].index[0]
                tgt_vac = df[(df['Unit']==u2) & (df['Desk']==d2) & (df['Status']=='VACANCY')]
                
                if not tgt_vac.empty:
                    t_idx = tgt_vac.index[0]
                    df.at[t_idx, 'Staff_Name'] = p; df.at[t_idx, 'Status'] = "Active"
                else:
                    df = pd.concat([df, pd.DataFrame([{"Unit":u2, "Desk":d2, "Staff_Name":p, "Status":"Active"}])], ignore_index=True)
                
                if old_act == "Mark VACANT":
                    df.at[src, 'Staff_Name'] = "VACANT POSITION"; df.at[src, 'Status'] = "VACANCY"; df.at[src, 'Action_Required'] = "Manpower Shortage"
                
                save_local(df); update_github(df); st.success("Transferred!"); st.rerun()

        elif act == "➕ Add Staff":
            u = st.selectbox("Unit", df['Unit'].unique())
            d = st.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
            n = st.text_input("Name")
            if st.button("Add"):
                vac = df[(df['Unit']==u) & (df['Desk']==d) & (df['Status']=='VACANCY')]
                if not vac.empty:
                    df.at[vac.index[0], 'Staff_Name'] = n; df.at[vac.index[0], 'Status'] = "Active"
                else:
                    df = pd.concat([df, pd.DataFrame([{"Unit":u, "Desk":d, "Staff_Name":n, "Status":"Active"}])], ignore_index=True)
                save_local(df); update_github(df); st.success("Added!"); st.rerun()
