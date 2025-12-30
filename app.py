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

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #0E1117; border: 1px solid #30333F; border-radius: 10px; padding: 15px; text-align: center; }
    .badge-vacant { background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .badge-transfer { background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .badge-active { background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .stButton>button { width: 100%; }
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

@st.cache_data
def load_data(filename):
    try:
        df = pd.read_csv(filename)
        # Ensure common columns exist
        if 'Status' not in df.columns: df['Status'] = 'Active'
        if 'Action_Required' not in df.columns: df['Action_Required'] = ''
        return df.fillna("")
    except: 
        if filename == DEPT_FILE: return pd.DataFrame(columns=['Department', 'Staff_Name', 'Designation', 'SAP_ID', 'Status', 'Action_Required'])
        return pd.DataFrame() # Fallback

def save_local(df, filename):
    df.to_csv(filename, index=False)
    st.cache_data.clear()

def format_staff_name(raw_name, desg=""):
    if "VACANT" in str(raw_name): return "VACANT"
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', str(raw_name), flags=re.IGNORECASE).strip()
    
    # If designation is provided in a separate column, append it
    if desg and str(desg).strip():
        # Check if desg already in name to avoid duplication
        if str(desg).lower() not in clean.lower():
            clean = f"{clean} ({desg})"
    else:
        # Try to extract from name if not provided
        pattern = r'\s+(JE|AE|DY\.? ?EE|ADD\.? ?EE|AD\.? ?EE|EE)\b'
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match: 
            clean = f"{clean[:match.start()].strip()} ({match.group(1)})"
            
    return clean

# --- CHART & ICON GENERATORS ---
def create_dashboard_charts(df, mode="Ops"):
    op_df = df[df['Desk'] != 'Shift In-Charge'] if mode == "Ops" else df
    
    # 1. Pie Chart (Status)
    fig1, ax1 = plt.subplots(figsize=(4, 3))
    status_counts = op_df['Status'].value_counts()
    colors_map = {'VACANCY':'#D32F2F', 'Transferred':'#F57C00', 'Active':'#388E3C', 'Long Leave':'#555'}
    pie_cols = [colors_map.get(x, '#999') for x in status_counts.index]
    ax1.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', colors=pie_cols, startangle=90)
    ax1.set_title('Overall Status', fontsize=10, fontweight='bold')
    
    # 2. Bar Chart
    fig2, ax2 = plt.subplots(figsize=(5, 3))
    if mode == "Ops":
        # Critical Gaps
        gaps = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
        if not gaps.empty:
            gap_counts = gaps.groupby(['Unit', 'Status']).size().unstack(fill_value=0)
            gap_counts.plot(kind='bar', stacked=False, color=[colors_map.get(x, 'red') for x in gap_counts.columns], ax=ax2)
            ax2.set_title('Critical Gaps', fontsize=10, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, "No Critical Gaps", ha='center', va='center')
            ax2.axis('off')
    else:
        # Department Strength
        dept_counts = op_df['Department'].value_counts().head(5) # Top 5
        dept_counts.plot(kind='bar', color='#2c3e50', ax=ax2)
        ax2.set_title('Top Departments (Strength)', fontsize=10, fontweight='bold')
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
def generate_pdf_report_lab(df, mode="Ops"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    # 1. Header
    report_title = "Operation Shift Report" if mode == "Ops" else "Departmental Staff List"
    story.append(Paragraph(f"MAHAGENCO Parli TPS - {report_title}", styles['Title']))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 15))

    # 2. Charts
    chart1, chart2 = create_dashboard_charts(df, mode)
    img1 = Image(chart1, width=200, height=150)
    img2 = Image(chart2, width=250, height=150)
    chart_table = Table([[img1, img2]], colWidths=[250, 250])
    chart_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(chart_table)
    story.append(Spacer(1, 20))

    if mode == "Ops":
        # OPERATIONAL ROSTER PDF LOGIC
        units = sorted(df['Unit'].unique())
        desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
        
        data = [['Position'] + units]
        # ... (Same Matrix Logic as before)
        # Simplified for brevity, reusing the robust matrix logic
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
                            sub_t = Table([[draw_red_cross(), Paragraph("<b>VACANT</b>", styles['Normal'])]], colWidths=[12, 70])
                            cell.append(sub_t)
                        elif r['Status'] == 'Transferred':
                            sub_t = Table([[draw_orange_flag(), Paragraph(f"<i>{nm}</i>", styles['Normal'])]], colWidths=[12, 70])
                            cell.append(sub_t)
                        else: cell.append(Paragraph(nm, styles['Normal']))
                row.append(cell)
            data.append(row)
        main_table = Table(data, colWidths=[100, 130, 130, 130])
        main_table.setStyle(TableStyle(t_style))
        story.append(main_table)

    else:
        # DEPARTMENTAL LIST PDF LOGIC
        story.append(Paragraph("Departmental Staff Breakdown", styles['Heading2']))
        depts = sorted(df['Department'].unique())
        
        for dept in depts:
            story.append(Paragraph(f"<b>{dept}</b>", styles['Heading3']))
            d_df = df[df['Department'] == dept]
            
            # Simple List Table
            d_data = [['Name', 'Designation', 'SAP ID', 'Status']]
            for _, r in d_df.iterrows():
                stat_style = "<b><font color='red'>VACANT</font></b>" if r['Status']=='VACANCY' else r['Status']
                d_data.append([r['Staff_Name'], r['Designation'], r['SAP_ID'], Paragraph(stat_style, styles['Normal'])])
            
            d_table = Table(d_data, colWidths=[200, 100, 100, 100])
            d_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ]))
            story.append(d_table)
            story.append(Spacer(1, 15))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# --- LOAD DATA ---
ops_df = load_data(OPS_FILE)
dept_df = load_data(DEPT_FILE)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/8/82/Mahagenco_Logo.png/220px-Mahagenco_Logo.png", width=100)
    st.title("Parli TPS Ops")
    
    # MODE SWITCHER
    view_mode = st.radio("Select View:", ["Shift Operations", "Departmental Staff"])
    
    st.divider()
    search_term = st.text_input("Search Staff")
    active_df = ops_df if view_mode == "Shift Operations" else dept_df
    
    if search_term and not active_df.empty:
        res = active_df[active_df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            st.success(f"Found {len(res)} matches:")
            for _, r in res.iterrows():
                loc = f"{r['Unit']} • {r['Desk']}" if view_mode=="Shift Operations" else f"{r['Department']}"
                st.markdown(f"**{format_staff_name(r['Staff_Name'])}**\n\n_{loc}_")
        else: st.warning("No match")
    
    st.divider()
    if not active_df.empty:
        if st.button("📄 Generate PDF"):
            with st.spinner("Generating..."):
                pdf_bytes = generate_pdf_report_lab(active_df, mode="Ops" if view_mode=="Shift Operations" else "Dept")
                st.download_button("⬇️ Download PDF", pdf_bytes, "Report.pdf", "application/pdf")

# --- MAIN PAGE ---
st.title(f"⚡ {view_mode}")

tab1, tab2, tab3 = st.tabs(["Dashboard", "Search", "Admin"])

with tab1:
    if view_mode == "Shift Operations":
        # --- OPS DASHBOARD ---
        op_df = ops_df[ops_df['Desk'] != 'Shift In-Charge']
        
        def agg_staff_html(x):
            html = []
            for _, row in x.iterrows():
                name = format_staff_name(row['Staff_Name'])
                if row['Status'] == 'VACANCY': html.append(f'<div class="badge-vacant">🔴 VACANT</div>')
                elif row['Status'] == 'Transferred': html.append(f'<div class="badge-transfer">🟠 {name}</div>')
                else: html.append(f'<div class="badge-active">👤 {name}</div>')
            return "".join(html)

        units = sorted(op_df['Unit'].unique())
        desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
        
        table_data = []
        for desk in desks:
            row = {"Desk": f"<b>{desk}</b>"}
            for unit in units:
                match = op_df[(op_df['Unit']==unit) & (op_df['Desk']==desk)]
                row[unit] = "-" if match.empty else agg_staff_html(match)
            table_data.append(row)
        
        st.write(pd.DataFrame(table_data).to_html(escape=False, index=False, classes="table table-bordered"), unsafe_allow_html=True)
        
        st.divider()
        c1, c2 = st.columns(2)
        c1.metric("Shortage", len(op_df[op_df['Status']=='VACANCY']))
        c2.metric("Transferred", len(op_df[op_df['Status']=='Transferred']))

    else:
        # --- DEPARTMENT DASHBOARD ---
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Department Strength")
            dept_counts = dept_df['Department'].value_counts().reset_index()
            dept_counts.columns = ['Department', 'Count']
            fig = px.bar(dept_counts, x='Department', y='Count', text_auto=True, color='Count')
            st.plotly_chart(fig, use_container_width=True)
        
        with c2:
            st.subheader("Designation Split")
            desg_counts = dept_df['Designation'].value_counts().reset_index()
            fig2 = px.pie(desg_counts, values='count', names='Designation', hole=0.4)
            st.plotly_chart(fig2, use_container_width=True)
            
        st.dataframe(dept_df, use_container_width=True, hide_index=True)

with tab3:
    st.header("Admin")
    if not st.session_state.admin_logged_in:
        if st.text_input("Pwd", type="password")=="admin123" and st.button("Login"):
            st.session_state.admin_logged_in=True
            st.rerun()
    else:
        if st.button("Logout"):
            st.session_state.admin_logged_in=False
            st.rerun()
            
        st.info(f"Editing: {view_mode}")
        working_df = ops_df if view_mode == "Shift Operations" else dept_df
        target_file = OPS_FILE if view_mode == "Shift Operations" else DEPT_FILE
        
        act = st.selectbox("Action", ["Change Status", "Add Person", "Remove/Transfer"])
        
        if act == "Change Status":
            # Simplified logic for brevity, adaptable to both
            if view_mode == "Shift Operations":
                u = st.selectbox("Unit", working_df['Unit'].unique())
                d = st.selectbox("Desk", working_df[working_df['Unit']==u]['Desk'].unique())
                p = st.selectbox("Person", working_df[(working_df['Unit']==u)&(working_df['Desk']==d)]['Staff_Name'].unique())
                idx = working_df[(working_df['Unit']==u)&(working_df['Desk']==d)&(working_df['Staff_Name']==p)].index[0]
            else:
                dept = st.selectbox("Dept", working_df['Department'].unique())
                p = st.selectbox("Person", working_df[working_df['Department']==dept]['Staff_Name'].unique())
                idx = working_df[(working_df['Department']==dept)&(working_df['Staff_Name']==p)].index[0]
                
            s = st.selectbox("Status", ["Active", "Transferred", "VACANCY"])
            if st.button("Update"):
                working_df.at[idx,'Status'] = s
                if s=='VACANCY': working_df.at[idx,'Staff_Name']="VACANT"
                save_local(working_df, target_file)
                update_github(working_df, target_file)
                st.success("Updated!")
                st.rerun()
