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
from reportlab.graphics.shapes import Drawing, Line, Polygon
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

@st.cache_data(ttl=60)
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

# --- CHART GENERATORS ---
def create_dashboard_charts(df, mode="Ops", filter_val=None):
    if df.empty: return None, None
    op_df = df
    if mode == VIEW_OPS:
        op_df = df[df['Desk'] != 'Shift In-Charge']
    elif filter_val and filter_val != "All":
        op_df = df[df['Department'] == filter_val]
    
    if op_df.empty: return None, None

    fig1, ax1 = plt.subplots(figsize=(4, 3))
    status_counts = op_df['Status'].value_counts()
    colors_map = {'VACANCY':'#D32F2F', 'Transferred':'#F57C00', 'Active':'#388E3C'}
    pie_cols = [colors_map.get(x, '#999') for x in status_counts.index]
    ax1.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', colors=pie_cols, startangle=90)
    ax1.set_title('Status', fontsize=10, fontweight='bold')
    
    fig2, ax2 = plt.subplots(figsize=(5, 3))
    if mode == VIEW_OPS:
        gaps = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
        if not gaps.empty and 'Unit' in gaps.columns:
            gap_counts = gaps.groupby(['Unit', 'Status']).size().unstack(fill_value=0)
            gap_counts.plot(kind='bar', stacked=False, color=[colors_map.get(x, 'red') for x in gap_counts.columns], ax=ax2)
            ax2.set_title('Critical Gaps', fontsize=10, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, "No Critical Gaps", ha='center', va='center')
            ax2.axis('off')
    else:
        if 'Designation' in op_df.columns:
            desg_counts = op_df['Designation'].value_counts().head(5)
            desg_counts.plot(kind='bar', color='#2c3e50', ax=ax2)
            ax2.set_title('Designation Split', fontsize=10, fontweight='bold')
            ax2.tick_params(axis='x', rotation=45, labelsize=8)

    f1 = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    f2 = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    fig1.savefig(f1.name, format='png', dpi=100, bbox_inches='tight')
    fig2.savefig(f2.name, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig1); plt.close(fig2)
    return f1.name, f2.name

def draw_red_cross():
    d = Drawing(10, 10)
    d.add(Line(1, 1, 9, 9, strokeColor=colors.red, strokeWidth=2))
    d.add(Line(1, 9, 9, 1, strokeColor=colors.red, strokeWidth=2))
    return d

def draw_orange_flag():
    d = Drawing(10, 10)
    d.add(Line(2, 0, 2, 10, strokeColor=colors.black, strokeWidth=1))
    d.add(Polygon([2, 10, 9, 7, 2, 4], fillColor=colors.orange, strokeWidth=0))
    return d

# --- PDF ENGINE ---
def generate_pdf_report_lab(df, mode="Ops", filter_val=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    title_text = "Shift Operations Report" if mode == VIEW_OPS else "Departmental Staff List"
    if filter_val and filter_val != "All": title_text += f" - {filter_val}"
    
    story.append(Paragraph(f"MAHAGENCO Parli TPS - {title_text}", styles['Title']))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 15))

    c1, c2 = create_dashboard_charts(df, mode, filter_val)
    if c1 and c2:
        img1 = Image(c1, width=200, height=150)
        img2 = Image(c2, width=250, height=150)
        story.append(Table([[img1, img2]], colWidths=[250, 250]))
        story.append(Spacer(1, 20))

    if mode == VIEW_OPS and not df.empty:
        units = sorted(df['Unit'].unique())
        desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
        data = [['Position'] + units]
        t_style = [('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]
        op_df = df[df['Desk'] != 'Shift In-Charge']
        for desk in desks:
            row = [Paragraph(f"<b>{desk}</b>", styles['Normal'])]
            for u in units:
                matches = op_df[(op_df['Unit'] == u) & (op_df['Desk'] == desk)]
                cell = []
                if matches.empty: cell.append(Paragraph("-", styles['Normal']))
                else:
                    for _, r in matches.iterrows():
                        nm = format_staff_name(r['Staff_Name'])
                        if r['Status'] == 'VACANCY':
                            cell.append(Table([[draw_red_cross(), Paragraph("<b>VACANT</b>", styles['Normal'])]], colWidths=[12, 70]))
                        elif r['Status'] == 'Transferred':
                            cell.append(Table([[draw_orange_flag(), Paragraph(f"<i>{nm}</i>", styles['Normal'])]], colWidths=[12, 70]))
                        else: cell.append(Paragraph(nm, styles['Normal']))
                row.append(cell)
            data.append(row)
        main_table = Table(data, colWidths=[100, 130, 130, 130])
        main_table.setStyle(TableStyle(t_style))
        story.append(main_table)
    elif not df.empty:
        # Departmental List PDF
        working_df = df
        if filter_val and filter_val != "All":
            working_df = df[df['Department'] == filter_val]
            
        depts = sorted(working_df['Department'].unique())
        for dept in depts:
            story.append(Paragraph(f"<b>{dept}</b>", styles['Heading3']))
            d_df = working_df[working_df['Department'] == dept].copy()
            d_df['Rank'] = d_df['Designation'].apply(get_rank_level)
            d_df = d_df.sort_values('Rank')
            
            d_data = [['Name', 'Designation', 'SAP ID', 'Status']]
            for _, r in d_df.iterrows():
                stat = r['Status']
                if stat == 'VACANCY': stat = "<font color='red'><b>VACANT</b></font>"
                elif stat == 'Transferred': stat = "<font color='orange'><b>Transferred</b></font>"
                d_data.append([r['Staff_Name'], r['Designation'], str(r['SAP_ID']), Paragraph(stat, styles['Normal'])])
            
            d_table = Table(d_data, colWidths=[180, 80, 80, 100])
            d_table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
            story.append(d_table)
            story.append(Spacer(1, 15))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# --- LOAD DATA ---
ops_df = load_data(OPS_FILE)
dept_df = load_data(DEPT_FILE)

# --- HEADER & NAVIGATION ---
st.title("⚡ Mahagenco Staffing Portal")

view_mode = st.radio("", [VIEW_OPS, VIEW_DEPT], horizontal=True, label_visibility="collapsed")
active_df = ops_df if view_mode == VIEW_OPS else dept_df

selected_dept = "All"
if view_mode == VIEW_DEPT and not dept_df.empty:
    depts = ["All"] + sorted(dept_df['Department'].unique().tolist())
    selected_dept = st.selectbox("Filter Department:", depts)
    if selected_dept != "All":
        active_df = active_df[active_df['Department'] == selected_dept]

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

with tab1:
    if view_mode == VIEW_OPS:
        # --- OPS DASHBOARD ---
        if ops_df.empty:
            st.error("Data Missing for Shift Ops.")
        else:
            op_df = ops_df[ops_df['Desk'] != 'Shift In-Charge']
            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            
            with c1:
                st.markdown("##### Staff Status")
                fig1 = px.pie(op_df['Status'].value_counts().reset_index(), values='count', names='Status', 
                              color='Status', color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4)
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
                m1.metric("Shortage", len(op_df[op_df['Status']=='VACANCY']))
                m2.metric("Transferred", len(op_df[op_df['Status']=='Transferred']))

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
        # --- DEPARTMENT DASHBOARD ---
        if dept_df.empty:
            st.error("Data Missing for Departments.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                dept_counts = active_df['Department'].value_counts().reset_index()
                dept_counts.columns = ['Department', 'Count']
                fig = px.bar(dept_counts, x='Department', y='Count', text_auto=True, color='Count', title="Department Strength")
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                desg_counts = active_df['Designation'].value_counts().head(5).reset_index()
                fig2 = px.pie(desg_counts, values='count', names='Designation', hole=0.4, title="Top Designations")
                st.plotly_chart(fig2, use_container_width=True)
            
            st.divider()
            st.subheader("🏛️ Departmental Staff Hierarchy")
            
            # Use unique departments for iteration
            all_departments = sorted(active_df['Department'].unique())
            
            # --- SPECIAL HANDLING FOR CHP FOLDERS ---
            chp_subfolders = [d for d in all_departments if 'CHP' in d]
            other_folders = [d for d in all_departments if 'CHP' not in d]
            
            # Render Non-CHP folders
            for dept_name in other_folders:
                group = active_df[active_df['Department'] == dept_name]
                if group.empty: continue
                
                with st.expander(f"📂 {dept_name} ({len(group)} Staff)", expanded=(selected_dept == dept_name)):
                    group = group.copy()
                    group['Rank'] = group['Designation'].apply(get_rank_level)
                    sorted_staff = group.sort_values(by='Rank')
                    
                    rank_labels = {
                        1: ("👑 Executive Engineer (EE)", "rank-ee"), 
                        2: ("⭐ Addl. Executive Engineer (AD.EE)", "rank-ad"),
                        3: ("🔷 Dy. Executive Engineer (DY.EE)", "rank-dy"),
                        4: ("🔧 Assistant Engineer (AE)", "rank-ae"),
                        5: ("🛠️ Junior Engineer (JE)", "rank-je"),
                        6: ("📋 Other Staff", "rank-je")
                    }
                    
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

            # Render CHP folders (if any exist and filter permits)
            if chp_subfolders and (selected_dept == "All" or "CHP" in selected_dept):
                # Just render them as normal folders now, no merging
                for dept_name in sorted(chp_subfolders):
                    group = active_df[active_df['Department'] == dept_name]
                    if group.empty: continue
                    
                    with st.expander(f"🏭 {dept_name} ({len(group)} Staff)", expanded=(selected_dept == dept_name)):
                        group = group.copy()
                        group['Rank'] = group['Designation'].apply(get_rank_level)
                        sorted_staff = group.sort_values(by='Rank')
                        
                        rank_labels = {
                            1: ("👑 Executive Engineer (EE)", "rank-ee"), 
                            2: ("⭐ Addl. Executive Engineer (AD.EE)", "rank-ad"),
                            3: ("🔷 Dy. Executive Engineer (DY.EE)", "rank-dy"),
                            4: ("🔧 Assistant Engineer (AE)", "rank-ae"),
                            5: ("🛠️ Junior Engineer (JE)", "rank-je"),
                            6: ("📋 Other Staff", "rank-je")
                        }
                        
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

with tab2:
    st.header("Search")
    search_term = st.text_input("Enter Name")
    combined_search = pd.DataFrame()
    if not ops_df.empty: combined_search = pd.concat([combined_search, ops_df.assign(Source='Ops')])
    if not dept_df.empty: combined_search = pd.concat([combined_search, dept_df.assign(Source='Dept')])
    
    if search_term and not combined_search.empty:
        res = combined_search[combined_search['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            for _, r in res.iterrows():
                if r['Source'] == 'Ops': loc = f"{r['Unit']} - {r['Desk']}" 
                else: loc = f"{r['Department']} ({r['Designation']})"
                st.info(f"**{format_staff_name(r['Staff_Name'])}** | {loc} | {r['Status']}")
        else: st.warning("No match")

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
            
            # --- ACTION: CHANGE STATUS ---
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
            
            # --- ACTION: ADD PERSON ---
            elif act == "Add Person":
                st.subheader("Add New Staff Member")
                if view_mode == VIEW_DEPT:
                    # Form for Departmental Staff
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
                        else:
                            st.error("Name is required.")
                            
                else:
                    # Form for Shift Operations (Ops)
                    c1, c2 = st.columns(2)
                    new_unit = c1.selectbox("Unit", ["Unit 6", "Unit 7", "Unit 8"])
                    new_desk = c2.selectbox("Desk", working_df['Desk'].unique())
                    new_name = st.text_input("Staff Name")
                    
                    if st.button("Add to Roster"):
                        if new_name:
                            # Check if seat is vacant to replace, else append
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
                        else:
                            st.error("Name is required.")

with st.sidebar:
    st.title("Report")
    if not active_df.empty:
        if st.button("📄 Generate PDF"):
            with st.spinner("Generating..."):
                pdf_bytes = generate_pdf_report_lab(active_df, mode="Ops" if view_mode==VIEW_OPS else "Dept", filter_val=selected_dept)
                st.download_button("⬇️ Download PDF", pdf_bytes, "Report.pdf", "application/pdf")
