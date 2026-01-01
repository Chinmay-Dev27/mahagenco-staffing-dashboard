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
from reportlab.lib.pagesizes import A4, landscape
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
    staff_only = df[df['Staff_Name'].str.contains("VACANT", case=False) == False].copy()
    
    # Sort Transferred first to prioritize that status on dedup
    staff_only['Status_Rank'] = staff_only['Status'].apply(lambda x: 2 if 'Transferred' in str(x) else 1)
    staff_only = staff_only.sort_values(by=['Staff_Name', 'Status_Rank'], ascending=[True, False])
    
    unique_staff = staff_only.drop_duplicates(subset=['Staff_Name'], keep='first')
    
    transferred = len(unique_staff[unique_staff['Status'] == 'Transferred'])
    vacant = len(df[df['Status'] == 'VACANCY'])
    
    status_counts = unique_staff['Status'].value_counts()
    if vacant > 0: status_counts['VACANCY'] = vacant
    
    return vacant, transferred, status_counts

# --- UNIFIED PDF ENGINE ---
def generate_combined_pdf(ops_df, dept_df, report_type="Summary"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading3']
    
    # --- Title Page ---
    story.append(Paragraph(f"MAHAGENCO Parli TPS - Consolidated Staffing Report", title_style))
    story.append(Paragraph(f"Type: {report_type} | Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 25))

    # --- PART 1: OVERALL SUMMARY ---
    # Combine metrics (safe filtering)
    ops_clean = ops_df[ops_df['Desk'] != 'Shift In-Charge'] if not ops_df.empty else pd.DataFrame(columns=['Staff_Name','Status'])
    v_ops, t_ops, _ = calculate_metrics(ops_clean)
    v_dept, t_dept, _ = calculate_metrics(dept_df)
    
    summary_data = [
        ['Section', 'Total Vacancies', 'Total Transferred'],
        ['Shift Operations', v_ops, t_ops],
        ['Departmental Staff', v_dept, t_dept],
        ['TOTAL', v_ops + v_dept, t_ops + t_dept]
    ]
    
    t_sum = Table(summary_data, colWidths=[200, 100, 100])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 30))

    # --- PART 2: SHIFT OPERATIONS ---
    story.append(Paragraph("1. Shift Operations (Main Plant)", styles['Heading2']))
    
    # Pull Shift In-Charge info from Dept DF (Robust source)
    sic_df = dept_df[dept_df['Department'].str.contains('Shift In-Charge')] if not dept_df.empty else pd.DataFrame()
    
    if not sic_df.empty:
        story.append(Paragraph("Shift In-Charge (EE)", heading_style))
        u67 = ", ".join(sic_df[sic_df['Department'] == 'Shift In-Charge (U6&7)']['Staff_Name'].unique())
        u8 = ", ".join(sic_df[sic_df['Department'] == 'Shift In-Charge (U8)']['Staff_Name'].unique())
        sic_data = [['Unit 6 & 7 (Common)', u67], ['Unit 8', u8]]
        t_sic = Table(sic_data, colWidths=[150, 400])
        t_sic.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (0,-1), colors.lightgrey)]))
        story.append(t_sic)
        story.append(Spacer(1, 10))

    if report_type == "Summary":
        agg_data = [['Unit', 'Active Staff', 'Vacant', 'Transferred']]
        if not ops_df.empty:
            groups = ops_df.groupby('Unit')
            for name, group in groups:
                v, t, s = calculate_metrics(group)
                active = s.get('Active', 0) if 'Active' in s else 0
                agg_data.append([name, active, v, t])
            
        t_agg = Table(agg_data, colWidths=[150, 100, 80, 100])
        t_agg.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
        story.append(t_agg)
    
    else:
        # Detailed Roster
        if not ops_df.empty:
            units = sorted(ops_df['Unit'].unique())
            desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            
            main_data = [['Position'] + units]
            for desk in desks:
                row = [desk]
                for u in units:
                    matches = ops_df[(ops_df['Unit'] == u) & (ops_df['Desk'] == desk)]
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
            
            t_main = Table(main_data, colWidths=[120, 180, 180, 180])
            t_main.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('FONTSIZE', (0,0), (-1,-1), 8),
            ]))
            story.append(t_main)

    story.append(PageBreak())

    # --- PART 3: DEPARTMENTAL STAFF ---
    story.append(Paragraph("2. Departmental Staff", styles['Heading2']))
    
    if not dept_df.empty:
        if report_type == "Summary":
            agg_data = [['Department', 'Active Staff', 'Vacant', 'Transferred']]
            groups = dept_df.groupby('Department')
            for name, group in groups:
                v, t, s = calculate_metrics(group)
                active = s.get('Active', 0) if 'Active' in s else 0
                agg_data.append([name, active, v, t])
                
            t_agg = Table(agg_data, colWidths=[250, 100, 80, 100])
            t_agg.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
            story.append(t_agg)
        else:
            depts = sorted(dept_df['Department'].unique())
            for d in depts:
                group = dept_df[dept_df['Department'] == d]
                if group.empty: continue
                
                story.append(Paragraph(f"{d} ({len(group)})", heading_style))
                d_data = [['Name', 'Designation', 'Status']]
                
                group = group.copy()
                group['Rank'] = group['Designation'].apply(get_rank_level)
                group = group.sort_values('Rank')
                
                for _, r in group.iterrows():
                    d_data.append([format_staff_name(r['Staff_Name']), str(r['Designation']), r['Status']])
                
                t_dept = Table(d_data, colWidths=[250, 150, 100])
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

if st.sidebar.button("📄 Generate Combined PDF"):
    with st.spinner("Generating..."):
        if ops_df.empty and dept_df.empty:
            st.sidebar.error("No data available.")
        else:
            pdf_bytes = generate_combined_pdf(ops_df, dept_df, report_type=report_type.split()[0])
            st.sidebar.download_button("⬇️ Download PDF", pdf_bytes, f"Full_Staffing_Report.pdf", "application/pdf")

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
                              color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4, height=250)
                st.plotly_chart(fig1, use_container_width=True)

            with c2:
                st.markdown("##### Gaps by Unit")
                gaps_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
                if not gaps_df.empty:
                    fig2 = px.histogram(gaps_df, x="Unit", color="Status", barmode="group",
                                        color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421'}, text_auto=True, height=250)
                    st.plotly_chart(fig2, use_container_width=True)
                else: st.success("No Manpower Gaps!")

            with c3:
                st.markdown("##### Metrics")
                m1, m2 = st.columns(2)
                m1.metric("Shortage", vacant_count)
                m2.metric("Transferred", transferred_count)

            # --- Shift In-Charge (Fetched from Dept DF now) ---
            st.subheader("👨‍✈️ Shift In-Charge (EE)")
            # Pull from DEPT DF now
            sic_dept = dept_df[dept_df['Department'].str.contains('Shift In-Charge')]
            
            u67_names = sic_dept[sic_dept['Department'] == 'Shift In-Charge (U6&7)']['Staff_Name'].unique()
            u8_names = sic_dept[sic_dept['Department'] == 'Shift In-Charge (U8)']['Staff_Name'].unique()
            
            sic_data = []
            max_len = max(len(u67_names), len(u8_names))
            for i in range(max_len):
                n67, s67_icon = "", ""
                if i < len(u67_names):
                    nm = u67_names[i]
                    n67 = format_staff_name(nm)
                    stat = sic_dept[sic_dept['Staff_Name'] == nm]['Status'].values
                    s67_icon = "🟠" if "Transferred" in stat else "🟢"

                n8, s8_icon = "", ""
                if i < len(u8_names):
                    nm = u8_names[i]
                    n8 = format_staff_name(nm)
                    stat = sic_dept[sic_dept['Staff_Name'] == nm]['Status'].values
                    s8_icon = "🟠" if "Transferred" in stat else "🟢"
                
                sic_data.append({
                    "Unit 6 & 7 (Common Pool)": f"{s67_icon} {n67}",
                    "Unit 8": f"{s8_icon} {n8}"
                })
            st.dataframe(pd.DataFrame(sic_data), use_container_width=True, hide_index=True)
            st.divider()

            # Roster Table
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
                fig = px.bar(dept_counts, x='Department', y='Count', text_auto=True, color='Count', title="Department Strength", height=350)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                desg_counts = active_df['Designation'].value_counts().head(5).reset_index()
                fig2 = px.pie(desg_counts, values='count', names='Designation', hole=0.4, title="Top Designations", height=350)
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
