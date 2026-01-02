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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
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

# --- CORE LOGIC: GLOBAL METRICS CALCULATION ---
def get_global_metrics(ops_df, dept_df, scope="Global"):
    """
    Calculates deduplicated metrics.
    scope: "Global", "Ops", "Dept"
    """
    # 1. Identify which data to include
    dfs_to_combine = []
    
    # Ops Data (Excluding Shift In-Charge from OPS file if they exist there, to avoid dups)
    if not ops_df.empty and (scope == "Global" or scope == "Ops"):
        # Ops file usually doesn't have Dept column, add placeholder
        clean_ops = ops_df[['Staff_Name', 'Status']].copy()
        dfs_to_combine.append(clean_ops)
        
    # Dept Data (Includes Shift In-Charge now)
    if not dept_df.empty:
        if scope == "Global":
            dfs_to_combine.append(dept_df[['Staff_Name', 'Status']])
        elif scope == "Ops":
            # For Ops view, we ONLY want Shift In-Charge from Dept file
            sic_only = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)][['Staff_Name', 'Status']]
            dfs_to_combine.append(sic_only)
        elif scope == "Dept":
            # For Dept view, include all dept staff
            dfs_to_combine.append(dept_df[['Staff_Name', 'Status']])

    if not dfs_to_combine:
        return 0, 0, pd.Series()

    combined = pd.concat(dfs_to_combine)
    
    # 2. Filter valid staff (exclude VACANT)
    staff_only = combined[combined['Staff_Name'].str.contains("VACANT", case=False) == False].copy()
    
    # 3. Deduplicate Logic: Prioritize 'Transferred' status
    # Assign rank: Transferred = 2, Active = 1
    staff_only['Status_Rank'] = staff_only['Status'].apply(lambda x: 2 if 'Transferred' in str(x) else 1)
    
    # Sort by Name then Rank Descending -> Transferred appears first for same name
    staff_only = staff_only.sort_values(by=['Staff_Name', 'Status_Rank'], ascending=[True, False])
    
    # Drop duplicates, keeping first (which is Transferred if it exists)
    unique_staff = staff_only.drop_duplicates(subset=['Staff_Name'], keep='first')
    
    # 4. Calculate Counts
    transferred = len(unique_staff[unique_staff['Status'] == 'Transferred'])
    
    # Vacancy Count (Position based, simple row count of VACANT)
    vacant = len(combined[combined['Status'] == 'VACANCY'])
    
    # Status Series for Charts
    status_counts = unique_staff['Status'].value_counts()
    if vacant > 0: status_counts['VACANCY'] = vacant
    
    return vacant, transferred, status_counts

# --- UNIFIED PDF ENGINE ---
def generate_pdf_report_lab(ops_df, dept_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading3']
    normal_style = styles['Normal']
    
    # --- Title Page ---
    story.append(Paragraph(f"MAHAGENCO Parli TPS - Consolidated Staffing Report", title_style))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", normal_style))
    story.append(Spacer(1, 20))

    # --- PART 1: GLOBAL SUMMARY ---
    # Calculate Global Stats
    v_total, t_total, _ = get_global_metrics(ops_df, dept_df, "Global")
    
    # Calculate Section Stats (approximate for display)
    v_ops, t_ops, _ = get_global_metrics(ops_df, dept_df, "Ops")
    v_dept, t_dept, _ = get_global_metrics(pd.DataFrame(), dept_df, "Dept") # Pass empty Ops to calc pure Dept
    
    summary_data = [
        ['Section', 'Total Vacancies', 'Total Transferred'],
        ['Shift Operations (Inc. In-Charge)', v_ops, t_ops],
        ['Departmental Staff', v_dept, t_dept],
        ['TOTAL PLANT', v_total, t_total]
    ]
    
    t_sum = Table(summary_data, colWidths=[250, 120, 120])
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
    
    # A. Shift In-Charge Table
    sic_df = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)]
    if not sic_df.empty:
        story.append(Paragraph("Shift In-Charge (EE)", heading_style))
        u67_rows = sic_df[sic_df['Department'] == 'Shift In-Charge (U6&7)']
        u8_rows = sic_df[sic_df['Department'] == 'Shift In-Charge (U8)']
        
        # Helper to format list with status
        def get_fmt_names(rows):
            names = []
            for _, r in rows.iterrows():
                n = format_staff_name(r['Staff_Name'])
                if r['Status'] == 'Transferred': n += " (Trf)"
                names.append(n)
            return ", ".join(names)

        sic_data = [
            ['Unit 6 & 7 (Common Pool)', get_fmt_names(u67_rows)],
            ['Unit 8', get_fmt_names(u8_rows)]
        ]
        t_sic = Table(sic_data, colWidths=[180, 450])
        t_sic.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (0,-1), colors.lightgrey), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(t_sic)
        story.append(Spacer(1, 15))

    # B. Main Roster
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
    story.append(Paragraph("2. Departmental Staff List", styles['Heading2']))
    
    if not dept_df.empty:
        # Sort depts to grouping
        depts = sorted(dept_df['Department'].unique())
        
        # Filter out Shift In-Charge from this list as it's shown above? 
        # User said "folders", let's show them all here for completeness but maybe note SIC is redundant.
        # Actually, let's just list them all cleanly.
        
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
                ('BOX', (0,0), (-1,-1), 1, colors.black),
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
if st.sidebar.button("📄 Generate PDF Report"):
    with st.spinner("Generating Report..."):
        pdf_bytes = generate_pdf_report_lab(ops_df, dept_df)
        st.sidebar.download_button("⬇️ Download PDF", pdf_bytes, "Staffing_Report.pdf", "application/pdf")

view_mode = st.radio("", [VIEW_OPS, VIEW_DEPT], horizontal=True, label_visibility="collapsed", key='view_mode')
active_df = ops_df if view_mode == VIEW_OPS else dept_df

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

with tab1:
    if view_mode == VIEW_OPS:
        if ops_df.empty:
            st.error("Data Missing for Shift Ops.")
        else:
            # --- METRICS CALCULATION (Including Shift In-Charge from Dept File) ---
            vacant_count, transferred_count, status_counts = get_global_metrics(ops_df, dept_df, "Ops")
            
            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            with c1:
                st.markdown("##### Staff Status")
                fig1 = px.pie(values=status_counts.values, names=status_counts.index, 
                              color=status_counts.index, 
                              color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4, height=350)
                st.plotly_chart(fig1, use_container_width=True)

            with c2:
                st.markdown("##### Gaps by Unit")
                # Filter just Ops DF for this chart
                op_view_df = ops_df[ops_df['Desk'] != 'Shift In-Charge']
                gaps_df = op_view_df[op_view_df['Status'].isin(['VACANCY', 'Transferred'])]
                if not gaps_df.empty:
                    fig2 = px.histogram(gaps_df, x="Unit", color="Status", barmode="group",
                                        color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421'}, text_auto=True, height=350)
                    st.plotly_chart(fig2, use_container_width=True)
                else: st.success("No Manpower Gaps!")

            with c3:
                st.markdown("##### Metrics")
                m1, m2 = st.columns(2)
                m1.metric("Shortage", vacant_count)
                m2.metric("Transferred", transferred_count)

            # --- Shift In-Charge (Fetched from Dept DF now) ---
            st.subheader("👨‍✈️ Shift In-Charge (EE)")
            sic_dept = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)]
            
            if not sic_dept.empty:
                u67_rows = sic_dept[sic_dept['Department'] == 'Shift In-Charge (U6&7)']
                u8_rows = sic_dept[sic_dept['Department'] == 'Shift In-Charge (U8)']
                
                u67_names = u67_rows['Staff_Name'].unique()
                u8_names = u8_rows['Staff_Name'].unique()
                
                sic_data = []
                max_len = max(len(u67_names), len(u8_names))
                for i in range(max_len):
                    n67, s67_icon = "", ""
                    if i < len(u67_names):
                        nm = u67_names[i]
                        n67 = format_staff_name(nm)
                        stat = u67_rows[u67_rows['Staff_Name'] == nm]['Status'].values
                        s67_icon = "🟠" if "Transferred" in stat else "🟢"

                    n8, s8_icon = "", ""
                    if i < len(u8_names):
                        nm = u8_names[i]
                        n8 = format_staff_name(nm)
                        stat = u8_rows[u8_rows['Staff_Name'] == nm]['Status'].values
                        s8_icon = "🟠" if "Transferred" in stat else "🟢"
                    
                    sic_data.append({
                        "Unit 6 & 7 (Common Pool)": f"{s67_icon} {n67}",
                        "Unit 8": f"{s8_icon} {n8}"
                    })
                st.dataframe(pd.DataFrame(sic_data), use_container_width=True, hide_index=True)
            else:
                st.info("Shift In-Charge data not found in Department file.")
            
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
            sic_folders = [d for d in all_departments if 'Shift In-Charge' in d]
            standard_folders = [d for d in all_departments if 'CHP' not in d and 'Main Plant Ops' not in d and 'Shift In-Charge' not in d]
            
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

            # 1. Shift In-Charge (Grouped)
            if sic_folders:
                sic_total = sum([len(active_df[active_df['Department'] == d]) for d in sic_folders])
                with st.expander(f"👨‍✈️ Shift In-Charge (Total: {sic_total})", expanded=False):
                    for d in sic_folders:
                        st.markdown(f"**{d}**")
                        render_hierarchy(active_df[active_df['Department'] == d])

            # 2. Main Plant Ops (Grouped)
            if ops_folders:
                ops_total = sum([len(active_df[active_df['Department'] == d]) for d in ops_folders])
                with st.expander(f"🏭 Main Plant PCR Staff (Total: {ops_total})", expanded=False):
                    ops_tabs = st.tabs([d.replace("Main Plant Ops - ", "") for d in ops_folders])
                    for i, dept_name in enumerate(ops_folders):
                        with ops_tabs[i]:
                            render_hierarchy(active_df[active_df['Department'] == dept_name])

            # 3. Coal Handling Plant (Grouped)
            if chp_folders:
                chp_total = sum([len(active_df[active_df['Department'] == d]) for d in chp_folders])
                with st.expander(f"🏭 Coal Handling Plant (Total: {chp_total})", expanded=False):
                    chp_tabs = st.tabs([d.replace("CHP", "").strip() for d in chp_folders])
                    for i, dept_name in enumerate(chp_folders):
                        with chp_tabs[i]:
                            render_hierarchy(active_df[active_df['Department'] == dept_name])

            # 4. Standard Folders
            for dept_name in standard_folders:
                group = active_df[active_df['Department'] == dept_name]
                if group.empty: continue
                with st.expander(f"📂 {dept_name} ({len(group)} Staff)", expanded=False):
                    render_hierarchy(group)

with tab2:
    st.header("Search & Reports")
    search_tabs = st.tabs(["⚡ Shift Operations Search", "🏢 Departmental Staff Search"])
    
    # 1. OPS SEARCH
    with search_tabs[0]:
        st.subheader("Search in Shift Operations")
        c_op1, c_op2 = st.columns(2)
        s_unit = c_op1.selectbox("Filter Unit", ["All"] + sorted(ops_df['Unit'].unique().tolist()), key="s_unit")
        s_desk = c_op2.selectbox("Filter Desk", ["All"] + sorted(ops_df['Desk'].unique().tolist()), key="s_desk")
        
        ops_filtered = ops_df.copy()
        if s_unit != "All": ops_filtered = ops_filtered[ops_filtered['Unit'] == s_unit]
        if s_desk != "All": ops_filtered = ops_filtered[ops_filtered['Desk'] == s_desk]
        
        if not ops_filtered.empty:
            c1, c2 = st.columns(2)
            with c1:
                # Deduplicated calculation for search results
                _, _, s_counts = calculate_metrics(ops_filtered)
                if not s_counts.empty:
                    fig_s = px.pie(values=s_counts.values, names=s_counts.index, color=s_counts.index, 
                                   color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, title="Status Distribution", height=250)
                    st.plotly_chart(fig_s, use_container_width=True)
            st.dataframe(ops_filtered[['Unit', 'Desk', 'Staff_Name', 'Status']], use_container_width=True, hide_index=True)
        else: st.info("No records found.")

    # 2. DEPT SEARCH
    with search_tabs[1]:
        st.subheader("Search in Departments")
        c_d1, c_d2 = st.columns(2)
        s_dept = c_d1.selectbox("Filter Department", ["All"] + sorted(dept_df['Department'].unique().tolist()), key="s_dept")
        
        dept_filtered = dept_df.copy()
        if s_dept != "All": dept_filtered = dept_filtered[dept_filtered['Department'] == s_dept]
        
        if not dept_filtered.empty:
            c1, c2 = st.columns(2)
            with c1:
                _, _, s_counts = calculate_metrics(dept_filtered)
                if not s_counts.empty:
                    fig_s = px.pie(values=s_counts.values, names=s_counts.index, color=s_counts.index, 
                                   color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, title="Status Distribution", height=250)
                    st.plotly_chart(fig_s, use_container_width=True)
            with c2:
                # Fix ValueError: Create clean DF for chart
                d_counts = dept_filtered['Designation'].value_counts().head(5)
                if not d_counts.empty:
                    chart_data = pd.DataFrame({'Role': d_counts.index, 'Count': d_counts.values})
                    fig_d = px.bar(chart_data, x='Role', y='Count', title="Top Roles", height=250)
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
