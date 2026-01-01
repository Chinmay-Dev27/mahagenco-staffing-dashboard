import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import re
from github import Github
import io
import tempfile

# --- REPORTLAB IMPORTS ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")
OPS_FILE = 'stitched_staffing_data.csv'
DEPT_FILE = 'departmental_staffing_data.csv'
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

# --- NAMES FOR VIEWS ---
VIEW_OPS = "PCR Shift Operation (Main Plant)"
VIEW_DEPT = "Departmental Staff"

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #0E1117; border: 1px solid #30333F; border-radius: 10px; padding: 15px; text-align: center; }
    .badge-vacant { background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .badge-transfer { background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .badge-active { background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .stButton>button { width: 100%; }
    div[data-testid="stRadio"] > label { font-size: 1.1rem; font-weight: bold; color: #4facfe; }
    
    /* Hierarchy Tree Styles */
    .rank-box { 
        padding: 5px 10px; margin: 2px 0; border-radius: 6px; text-align: left; color: white; font-weight: bold; font-size: 0.9em; display: flex; align-items: center;
    }
    .rank-ee { background-color: #1565C0; border-left: 4px solid #90CAF9; } 
    .rank-ad { background-color: #1976D2; border-left: 4px solid #64B5F6; margin-left: 15px; }
    .rank-dy { background-color: #1E88E5; border-left: 4px solid #42A5F5; margin-left: 30px; }
    .rank-ae { background-color: #0277BD; border-left: 4px solid #4FC3F7; margin-left: 45px; }
    .rank-je { background-color: #00838F; border-left: 4px solid #26C6DA; margin-left: 60px; }
    .staff-name { font-weight: normal; margin-left: 10px; color: #fff; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'admin_logged_in' not in st.session_state: st.session_state.admin_logged_in = False

# --- DATA FUNCTIONS ---
def update_github(df, filename):
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(filename)
            repo.update_file(contents.path, f"Admin Update {filename}", df.to_csv(index=False), contents.sha)
        except:
            repo.create_file(filename, "Initial Commit", df.to_csv(index=False))
        return True
    except Exception as e:
        st.error(f"GitHub Sync Error: {e}")
        return False

@st.cache_data(ttl=1) 
def load_data(filename):
    try:
        df = pd.read_csv(filename)
        if filename == OPS_FILE and 'Desk' not in df.columns: return pd.DataFrame()
        if 'Status' not in df.columns: df['Status'] = 'Active'
        if 'Action_Required' not in df.columns: df['Action_Required'] = ''
        return df.fillna("")
    except:
        if filename == DEPT_FILE: return pd.DataFrame(columns=['Department', 'Staff_Name', 'Designation', 'SAP_ID', 'Status', 'Action_Required'])
        if filename == OPS_FILE: return pd.DataFrame(columns=['Unit', 'Desk', 'Staff_Name', 'Status', 'Action_Required'])
        return pd.DataFrame()

def save_local(df, filename):
    df.to_csv(filename, index=False)
    st.cache_data.clear()

def format_staff_name(raw_name, desg=""):
    if "VACANT" in str(raw_name): return "VACANT"
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', str(raw_name), flags=re.IGNORECASE).strip()
    if desg and str(desg).strip() and str(desg).lower() not in clean.lower():
        clean = f"{clean} ({desg})"
    elif not desg:
        pattern = r'\s+(JE|AE|DY\.? ?EE|ADD\.? ?EE|AD\.? ?EE|EE)\b'
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match: clean = f"{clean[:match.start()].strip()} ({match.group(1)})"
    return clean

def get_rank_level(desg):
    d = str(desg).upper().replace('.', '').strip()
    if 'EXECUTIVE' in d or 'EE' in d:
        if 'ADD' in d or 'AD' in d: return 2
        if 'DY' in d: return 3
        if d == 'EE' or d == 'EXECUTIVE ENGINEER': return 1
    if 'AE' in d or 'ASSISTANT' in d: return 4
    if 'JE' in d or 'JUNIOR' in d: return 5
    return 6

# --- HELPER: CALCULATE METRICS (DEDUPLICATED) ---
def calculate_metrics(df, mode="Ops"):
    if df.empty: return 0, 0, pd.Series()
    staff_only = df[df['Staff_Name'].str.contains("VACANT", case=False) == False]
    
    # Sort by Status (Transferred first) then deduplicate by Name
    # This ensures if a person is listed as Active AND Transferred, we count them as Transferred.
    unique_staff = staff_only.sort_values('Status', ascending=False).drop_duplicates(subset=['Staff_Name'], keep='first')
    
    transferred = len(unique_staff[unique_staff['Status'] == 'Transferred'])
    vacant = len(df[df['Status'] == 'VACANCY'])
    
    # Recalculate status counts based on unique list
    status_counts = unique_staff['Status'].value_counts()
    if vacant > 0: status_counts['VACANCY'] = vacant
    
    return vacant, transferred, status_counts

# --- PDF ENGINE (FULL REPORT) ---
def generate_pdf_report_lab(df, mode="Ops", report_type="Summary"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading3']
    normal_style = styles['Normal']
    
    # --- Header ---
    title_text = "Shift Operations Report" if mode == VIEW_OPS else "Departmental Staff List"
    story.append(Paragraph(f"MAHAGENCO Parli TPS - {title_text}", title_style))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", normal_style))
    story.append(Spacer(1, 20))

    # --- Summary Metrics ---
    vac, trf, stats = calculate_metrics(df, mode)
    summary_data = [
        ['Total Positions', 'Active Staff', 'Transferred', 'Vacant'],
        [len(df), stats.get('Active', 0), trf, vac]
    ]
    t_sum = Table(summary_data, colWidths=[120, 120, 120, 120])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 25))

    # --- Content ---
    if report_type == "Summary":
        story.append(Paragraph("Vacancy & Strength Breakdown", heading_style))
        # Group by Unit/Desk/Dept
        agg_data = [['Section', 'Active', 'Vacant', 'Transferred']]
        
        if mode == VIEW_OPS:
            groups = df.groupby(['Unit'])
            for name, group in groups:
                v, t, s = calculate_metrics(group)
                agg_data.append([name, s.get('Active', 0), v, t])
        else:
            groups = df.groupby(['Department'])
            for name, group in groups:
                v, t, s = calculate_metrics(group)
                agg_data.append([name, s.get('Active', 0), v, t])
                
        t_agg = Table(agg_data, colWidths=[250, 80, 80, 80])
        t_agg.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(t_agg)

    else: # Detailed Report
        story.append(Paragraph("Detailed Roster", heading_style))
        
        if mode == VIEW_OPS:
            # Ops Table Logic
            units = sorted(df['Unit'].unique()) if 'Unit' in df.columns else []
            desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            
            main_data = [['Position'] + units]
            for desk in desks:
                row = [desk]
                for u in units:
                    matches = df[(df['Unit'] == u) & (df['Desk'] == desk)]
                    if matches.empty:
                        row.append("-")
                    else:
                        names = []
                        for _, r in matches.iterrows():
                            nm = format_staff_name(r['Staff_Name'])
                            if r['Status'] == 'VACANCY': nm = "VACANT"
                            elif r['Status'] == 'Transferred': nm = f"{nm} (Trf)"
                            names.append(nm)
                        row.append("\n".join(names))
                main_data.append(row)
            
            t_main = Table(main_data, colWidths=[120, 130, 130, 130])
            t_main.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
            ]))
            story.append(t_main)
            
        else:
            # Dept Table Logic
            depts = sorted(df['Department'].unique()) if 'Department' in df.columns else []
            for d in depts:
                group = df[df['Department'] == d]
                if group.empty: continue
                story.append(Paragraph(f"{d}", heading_style))
                d_data = [['Name', 'Designation', 'Status']]
                
                group = group.copy()
                group['Rank'] = group['Designation'].apply(get_rank_level)
                group = group.sort_values('Rank')
                
                for _, r in group.iterrows():
                    d_data.append([format_staff_name(r['Staff_Name']), str(r['Designation']), r['Status']])
                
                t_dept = Table(d_data, colWidths=[200, 150, 100])
                t_dept.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ]))
                story.append(t_dept)
                story.append(Spacer(1, 15))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# --- LOAD DATA ---
ops_df = load_data(OPS_FILE)
dept_df = load_data(DEPT_FILE)

# --- HEADER & NAVIGATION ---
st.title("⚡ Mahagenco Staffing Portal")

# Sidebar
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("Report Options")
report_type = st.sidebar.radio("PDF Type", ["Summary (Numbers)", "Detailed (Names)"])

if st.sidebar.button("📄 Generate PDF"):
    with st.spinner("Generating..."):
        active_df_pdf = ops_df if st.session_state.get('view_mode', VIEW_OPS) == VIEW_OPS else dept_df
        # Safety check for empty dataframe
        if active_df_pdf.empty:
            st.sidebar.error("No data to generate report.")
        else:
            pdf_bytes = generate_pdf_report_lab(
                active_df_pdf, 
                mode="Ops" if st.session_state.get('view_mode', VIEW_OPS) == VIEW_OPS else "Dept", 
                report_type=report_type.split()[0]
            )
            st.sidebar.download_button("⬇️ Download PDF", pdf_bytes, f"Staff_Report_{report_type.split()[0]}.pdf", "application/pdf")

# View Selector
view_mode = st.radio("", [VIEW_OPS, VIEW_DEPT], horizontal=True, label_visibility="collapsed", key='view_mode')
active_df = ops_df if view_mode == VIEW_OPS else dept_df

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

with tab1:
    if view_mode == VIEW_OPS:
        if ops_df.empty:
            st.error("Data Missing for Shift Ops.")
        else:
            op_df = ops_df[ops_df['Desk'] != 'Shift In-Charge']
            vacant_count, transferred_count, status_counts = calculate_metrics(op_df, VIEW_OPS)
            
            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            with c1:
                st.markdown("##### Staff Status")
                fig1 = px.pie(values=status_counts.values, names=status_counts.index, 
                              color=status_counts.index, 
                              color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4)
                fig1.update_layout(showlegend=False, margin=dict(t=0,b=0), height=150)
                st.plotly_chart(fig1, use_container_width=True)

            with c2:
                st.markdown("##### Gaps by Unit")
                gaps_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
                if not gaps_df.empty:
                    fig2 = px.histogram(gaps_df, x="Unit", color="Status", barmode="group",
                                        color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421'}, text_auto=True)
                    fig2.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False, margin=dict(t=10,b=10), height=150)
                    st.plotly_chart(fig2, use_container_width=True)
                else: st.success("No Manpower Gaps!")

            with c3:
                st.markdown("##### Metrics")
                m1, m2 = st.columns(2)
                m1.metric("Shortage", vacant_count)
                m2.metric("Transferred", transferred_count)

            # Shift In-Charge
            st.subheader("👨‍✈️ Shift In-Charge (EE)")
            sic_df = ops_df[ops_df['Desk'] == 'Shift In-Charge']
            u67_names = sic_df[sic_df['Unit'].isin(['Unit 6', 'Unit 7'])]['Staff_Name'].unique()
            u8_names = sic_df[sic_df['Unit'] == 'Unit 8']['Staff_Name'].unique()
            
            sic_data = []
            max_len = max(len(u67_names), len(u8_names))
            for i in range(max_len):
                n67, s67_icon = "", ""
                if i < len(u67_names):
                    nm = u67_names[i]
                    n67 = format_staff_name(nm)
                    stat = sic_df[sic_df['Staff_Name'] == nm]['Status'].values
                    s67_icon = "🟠" if "Transferred" in stat else "🟢"

                n8, s8_icon = "", ""
                if i < len(u8_names):
                    nm = u8_names[i]
                    n8 = format_staff_name(nm)
                    stat = sic_df[sic_df['Staff_Name'] == nm]['Status'].values
                    s8_icon = "🟠" if "Transferred" in stat else "🟢"
                
                sic_data.append({
                    "Unit 6 & 7 (Common Pool)": f"{s67_icon} {n67}",
                    "Unit 8": f"{s8_icon} {n8}"
                })
            st.dataframe(pd.DataFrame(sic_data), use_container_width=True, hide_index=True)
            st.divider()

            # Roster
            def agg_staff_html(x):
                html = []
                for _, row in x.iterrows():
                    name = format_staff_name(row['Staff_Name'])
                    if row['Status'] == 'VACANCY': html.append(f'<div class="badge-vacant">🔴 VACANT</div>')
                    elif row['Status'] == 'Transferred': html.append(f'<div class="badge-transfer">🟠 {name}</div>')
                    else: html.append(f'<div class="badge-active">👤 {name}</div>')
                return "".join(html)

            units = sorted(op_df['Unit'].unique())
            desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            table_data = []
            for desk in desks:
                row = {"Desk": f"<b>{desk}</b>"}
                for unit in units:
                    match = op_df[(op_df['Unit']==unit) & (op_df['Desk']==desk)]
                    row[unit] = "-" if match.empty else agg_staff_html(match)
                table_data.append(row)
            st.write(pd.DataFrame(table_data).to_html(escape=False, index=False, classes="table table-bordered"), unsafe_allow_html=True)

    else:
        # --- DEPT DASHBOARD ---
        if dept_df.empty:
            st.error("Data Missing.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                chart_df = active_df.copy()
                chart_df.loc[chart_df['Department'].str.contains('CHP'), 'Department'] = 'Coal Handling Plant'
                dept_counts = chart_df['Department'].value_counts().reset_index()
                dept_counts.columns = ['Department', 'Count']
                fig = px.bar(dept_counts, x='Department', y='Count', text_auto=True, color='Count', title="Department Strength")
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                desg_counts = active_df['Designation'].value_counts().head(5).reset_index()
                fig2 = px.pie(desg_counts, values='count', names='Designation', hole=0.4, title="Top Designations")
                st.plotly_chart(fig2, use_container_width=True)
            
            st.divider()
            st.subheader("🏛️ Departmental Staff Hierarchy")
            
            all_departments = sorted(active_df['Department'].unique())
            chp_folders = [d for d in all_departments if 'CHP' in d]
            ops_folders = [d for d in all_departments if 'Main Plant Ops' in d]
            standard_folders = [d for d in all_departments if 'CHP' not in d and 'Main Plant Ops' not in d]
            
            def render_hierarchy(group):
                group = group.copy()
                group['Rank'] = group['Designation'].apply(get_rank_level)
                sorted_staff = group.sort_values(by='Rank')
                rank_labels = {1: ("👑 Executive Engineer (EE)", "rank-ee"), 2: ("⭐ Addl. Executive Engineer (AD.EE)", "rank-ad"), 3: ("🔷 Dy. Executive Engineer (DY.EE)", "rank-dy"), 4: ("🔧 Assistant Engineer (AE)", "rank-ae"), 5: ("🛠️ Junior Engineer (JE)", "rank-je"), 6: ("📋 Other Staff", "rank-je")}
                for rank in range(1, 7):
                    sub_group = sorted_staff[sorted_staff['Rank'] == rank]
                    if not sub_group.empty:
                        label, css_class = rank_labels[rank]
                        st.markdown(f'<div class="rank-box {css_class}">{label}</div>', unsafe_allow_html=True)
                        cols = st.columns(3)
                        for i, (_, row) in enumerate(sub_group.iterrows()):
                            name = format_staff_name(row['Staff_Name'])
                            status_icon = "🔴" if row['Status'] == 'VACANCY' else "🟠" if row['Status'] == 'Transferred' else "🟢"
                            cols[i % 3].markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{status_icon} **{name}**")

            if ops_folders:
                ops_total = sum([len(active_df[active_df['Department'] == d]) for d in ops_folders])
                with st.expander(f"🏭 Main Plant PCR Staff (Total: {ops_total})", expanded=False):
                    ops_tabs = st.tabs([d.replace("Main Plant Ops - ", "") for d in ops_folders])
                    for i, dept_name in enumerate(ops_folders):
                        with ops_tabs[i]:
                            render_hierarchy(active_df[active_df['Department'] == dept_name])

            if chp_folders:
                chp_total = sum([len(active_df[active_df['Department'] == d]) for d in chp_folders])
                with st.expander(f"🏭 Coal Handling Plant (Total: {chp_total})", expanded=False):
                    chp_tabs = st.tabs([d.replace("CHP", "").strip() for d in chp_folders])
                    for i, dept_name in enumerate(chp_folders):
                        with chp_tabs[i]:
                            render_hierarchy(active_df[active_df['Department'] == dept_name])

            for dept_name in standard_folders:
                group = active_df[active_df['Department'] == dept_name]
                if group.empty: continue
                with st.expander(f"📂 {dept_name} ({len(group)} Staff)", expanded=False):
                    render_hierarchy(group)

with tab2:
    st.header("Search & Reports")
    
    # SEPARATE TABS TO AVOID DATAFRAME CONFLICTS
    search_tabs = st.tabs(["⚡ Shift Operations Search", "🏢 Departmental Staff Search"])
    
    # 1. OPS SEARCH
    with search_tabs[0]:
        st.subheader("Search in Shift Operations")
        c_op1, c_op2, c_op3 = st.columns(3)
        s_unit = c_op1.selectbox("Filter Unit", ["All"] + sorted(ops_df['Unit'].unique().tolist()), key="s_unit")
        s_desk = c_op2.selectbox("Filter Desk", ["All"] + sorted(ops_df['Desk'].unique().tolist()), key="s_desk")
        s_name = c_op3.text_input("Search Name", key="s_name_op")
        
        ops_filtered = ops_df.copy()
        if s_unit != "All": ops_filtered = ops_filtered[ops_filtered['Unit'] == s_unit]
        if s_desk != "All": ops_filtered = ops_filtered[ops_filtered['Desk'] == s_desk]
        if s_name: ops_filtered = ops_filtered[ops_filtered['Staff_Name'].str.contains(s_name, case=False, na=False)]
        
        if not ops_filtered.empty:
            c1, c2 = st.columns(2)
            with c1:
                s_counts = ops_filtered['Status'].value_counts()
                fig_s = px.pie(values=s_counts.values, names=s_counts.index, color=s_counts.index, 
                               color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, title="Status", height=200)
                st.plotly_chart(fig_s, use_container_width=True)
            st.dataframe(ops_filtered[['Unit', 'Desk', 'Staff_Name', 'Status']], use_container_width=True, hide_index=True)
        else: st.info("No records found.")

    # 2. DEPT SEARCH
    with search_tabs[1]:
        st.subheader("Search in Departments")
        c_d1, c_d2 = st.columns(2)
        s_dept = c_d1.selectbox("Filter Department", ["All"] + sorted(dept_df['Department'].unique().tolist()), key="s_dept")
        s_dname = c_d2.text_input("Search Name", key="s_name_dept")
        
        dept_filtered = dept_df.copy()
        if s_dept != "All": dept_filtered = dept_filtered[dept_filtered['Department'] == s_dept]
        if s_dname: dept_filtered = dept_filtered[dept_filtered['Staff_Name'].str.contains(s_dname, case=False, na=False)]
        
        if not dept_filtered.empty:
            c1, c2 = st.columns(2)
            with c1:
                s_counts = dept_filtered['Status'].value_counts()
                fig_s = px.pie(values=s_counts.values, names=s_counts.index, color=s_counts.index, 
                               color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, title="Status", height=200)
                st.plotly_chart(fig_s, use_container_width=True)
            with c2:
                # Fix ValueError: Create clean DF for chart
                d_counts = dept_filtered['Designation'].value_counts().head(5)
                chart_data = pd.DataFrame({'Role': d_counts.index, 'Count': d_counts.values})
                fig_d = px.bar(chart_data, x='Role', y='Count', title="Top Roles", height=200)
                st.plotly_chart(fig_d, use_container_width=True)
            st.dataframe(dept_filtered[['Department', 'Staff_Name', 'Designation', 'Status']], use_container_width=True, hide_index=True)
        else: st.info("No records found.")

with tab3:
    st.header("Admin")
    if not st.session_state.admin_logged_in:
        if st.text_input("Password", type="password")=="admin123" and st.button("Login"):
            st.session_state.admin_logged_in=True
            st.rerun()
    else:
        if st.button("Logout"):
            st.session_state.admin_logged_in=False
            st.rerun()
            
        st.write(f"Editing: **{view_mode}**")
        working_df = ops_df if view_mode == VIEW_OPS else dept_df
        target_file = OPS_FILE if view_mode == VIEW_OPS else DEPT_FILE
        
        if working_df.empty:
            st.error("Cannot edit empty dataset.")
        else:
            act = st.selectbox("Action", ["Change Status", "Add Person"])
            if act == "Change Status":
                if view_mode == VIEW_OPS:
                    u = st.selectbox("Unit", working_df['Unit'].unique())
                    d = st.selectbox("Desk", working_df[working_df['Unit']==u]['Desk'].unique())
                    p_list = working_df[(working_df['Unit']==u)&(working_df['Desk']==d)]
                else:
                    dept = st.selectbox("Department", working_df['Department'].unique())
                    p_list = working_df[working_df['Department']==dept]
                
                if not p_list.empty:
                    p = st.selectbox("Person", p_list['Staff_Name'].unique())
                    s = st.selectbox("New Status", ["Active", "Transferred", "VACANCY"])
                    if st.button("Update Status"):
                        idx = p_list[p_list['Staff_Name']==p].index[0]
                        working_df.at[idx,'Status'] = s
                        if s=='VACANCY': working_df.at[idx,'Staff_Name']="VACANT"
                        save_local(working_df, target_file)
                        update_github(working_df, target_file)
                        st.success("Updated!")
                        st.rerun()
            elif act == "Add Person":
                st.subheader("Add New Staff Member")
                if view_mode == VIEW_DEPT:
                    c1, c2 = st.columns(2)
                    new_dept = c1.selectbox("Select Department", sorted(working_df['Department'].unique()))
                    new_name = c2.text_input("Full Name")
                    c3, c4 = st.columns(2)
                    new_desg = c3.selectbox("Designation", ["EE", "AD.EE", "DY.EE", "AE", "JE", "Other"])
                    new_sap = c4.text_input("SAP ID (Optional)")
                    if st.button("Add to Department"):
                        if new_name:
                            new_row = {"Department": new_dept, "Staff_Name": new_name, "Designation": new_desg, "SAP_ID": new_sap, "Status": "Active", "Action_Required": ""}
                            working_df = pd.concat([working_df, pd.DataFrame([new_row])], ignore_index=True)
                            save_local(working_df, target_file)
                            update_github(working_df, target_file)
                            st.success(f"Added {new_name} to {new_dept}")
                            st.rerun()
                        else: st.error("Name is required.")
                else:
                    c1, c2 = st.columns(2)
                    new_unit = c1.selectbox("Unit", ["Unit 6", "Unit 7", "Unit 8"])
                    new_desk = c2.selectbox("Desk", working_df['Desk'].unique())
                    new_name = st.text_input("Staff Name")
                    if st.button("Add to Roster"):
                        if new_name:
                            vac_check = working_df[(working_df['Unit']==new_unit) & (working_df['Desk']==new_desk) & (working_df['Status']=='VACANCY')]
                            if not vac_check.empty:
                                idx = vac_check.index[0]
                                working_df.at[idx, 'Staff_Name'] = new_name
                                working_df.at[idx, 'Status'] = "Active"
                            else:
                                new_row = {"Unit": new_unit, "Desk": new_desk, "Staff_Name": new_name, "Status": "Active", "Action_Required": ""}
                                working_df = pd.concat([working_df, pd.DataFrame([new_row])], ignore_index=True)
                            save_local(working_df, target_file)
                            update_github(working_df, target_file)
                            st.success(f"Added {new_name} to {new_desk}")
                            st.rerun()
                        else: st.error("Name is required.")
