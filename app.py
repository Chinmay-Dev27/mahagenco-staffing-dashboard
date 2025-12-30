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
    
    /* Highlight the view switcher */
    div[data-testid="stRadio"] > label { font-size: 1.2rem; font-weight: bold; color: #4facfe; }
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
        if 'Status' not in df.columns: df['Status'] = 'Active'
        if 'Action_Required' not in df.columns: df['Action_Required'] = ''
        return df.fillna("")
    except: 
        if filename == DEPT_FILE: return pd.DataFrame(columns=['Department', 'Staff_Name', 'Designation', 'SAP_ID', 'Status', 'Action_Required'])
        return pd.DataFrame()

def save_local(df, filename):
    df.to_csv(filename, index=False)
    st.cache_data.clear()

def format_staff_name(raw_name, desg=""):
    if "VACANT" in str(raw_name): return "VACANT"
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', str(raw_name), flags=re.IGNORECASE).strip()
    
    # Auto-add designation if not present
    if desg and str(desg).strip() and str(desg).lower() not in clean.lower():
        clean = f"{clean} ({desg})"
    elif not desg:
        pattern = r'\s+(JE|AE|DY\.? ?EE|ADD\.? ?EE|AD\.? ?EE|EE)\b'
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match: clean = f"{clean[:match.start()].strip()} ({match.group(1)})"
            
    return clean

# --- CHART GENERATORS ---
def create_dashboard_charts(df, mode="Ops"):
    op_df = df[df['Desk'] != 'Shift In-Charge'] if mode == "Ops" else df
    
    # 1. Pie Chart
    fig1, ax1 = plt.subplots(figsize=(4, 3))
    status_counts = op_df['Status'].value_counts()
    colors_map = {'VACANCY':'#D32F2F', 'Transferred':'#F57C00', 'Active':'#388E3C'}
    pie_cols = [colors_map.get(x, '#999') for x in status_counts.index]
    ax1.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', colors=pie_cols, startangle=90)
    ax1.set_title('Overall Status', fontsize=10, fontweight='bold')
    
    # 2. Bar Chart
    fig2, ax2 = plt.subplots(figsize=(5, 3))
    if mode == "Ops":
        gaps = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
        if not gaps.empty:
            gap_counts = gaps.groupby(['Unit', 'Status']).size().unstack(fill_value=0)
            gap_counts.plot(kind='bar', stacked=False, color=[colors_map.get(x, 'red') for x in gap_counts.columns], ax=ax2)
            ax2.set_title('Critical Gaps', fontsize=10, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, "No Critical Gaps", ha='center', va='center')
            ax2.axis('off')
    else:
        # Dept Strength
        dept_counts = op_df['Department'].value_counts().head(7)
        dept_counts.plot(kind='bar', color='#2c3e50', ax=ax2)
        ax2.set_title('Staff Strength by Dept', fontsize=10, fontweight='bold')
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
    
    title_text = "Shift Operations Report" if mode == "Ops" else "Departmental Staff List"
    story.append(Paragraph(f"MAHAGENCO Parli TPS - {title_text}", styles['Title']))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 15))

    chart1, chart2 = create_dashboard_charts(df, mode)
    img1 = Image(chart1, width=200, height=150)
    img2 = Image(chart2, width=250, height=150)
    story.append(Table([[img1, img2]], colWidths=[250, 250]))
    story.append(Spacer(1, 20))

    if mode == "Ops":
        # Matrix Table Code (Preserved from previous correct version)
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
    else:
        # Departmental List
        depts = sorted(df['Department'].unique())
        for dept in depts:
            story.append(Paragraph(f"<b>{dept}</b>", styles['Heading3']))
            d_df = df[df['Department'] == dept]
            d_data = [['Name', 'Designation', 'SAP ID', 'Status']]
            for _, r in d_df.iterrows():
                stat = r['Status']
                if stat == 'VACANCY': stat = "<font color='red'><b>VACANT</b></font>"
                elif stat == 'Transferred': stat = "<font color='orange'><b>Transferred</b></font>"
                d_data.append([r['Staff_Name'], r['Designation'], str(r['SAP_ID']), Paragraph(stat, styles['Normal'])])
            
            d_table = Table(d_data, colWidths=[180, 80, 80, 100])
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

# --- HEADER & NAVIGATION ---
st.title("⚡ Mahagenco Staffing Portal")

# TOP-LEVEL NAVIGATION (Front Page Visibility)
view_mode = st.radio("", ["Shift Operations", "Departmental Staff"], horizontal=True, label_visibility="collapsed")
active_df = ops_df if view_mode == "Shift Operations" else dept_df

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

with tab1:
    if view_mode == "Shift Operations":
        # OPS DASHBOARD (Restored Visuals)
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
        # DEPT DASHBOARD
        c1, c2 = st.columns([2, 1])
        with c1:
            dept_counts = dept_df['Department'].value_counts().reset_index()
            dept_counts.columns = ['Department', 'Count']
            fig = px.bar(dept_counts, x='Department', y='Count', text_auto=True, color='Count', title="Department Strength")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            desg_counts = dept_df['Designation'].value_counts().head(5).reset_index()
            fig2 = px.pie(desg_counts, values='count', names='Designation', hole=0.4, title="Top Designations")
            st.plotly_chart(fig2, use_container_width=True)
            
        st.dataframe(dept_df, use_container_width=True, hide_index=True)

with tab2:
    st.header("Search")
    search_term = st.text_input("Enter Name")
    if search_term and not active_df.empty:
        res = active_df[active_df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            for _, r in res.iterrows():
                loc = f"{r['Unit']} - {r['Desk']}" if view_mode == "Shift Operations" else f"{r['Department']}"
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
        working_df = ops_df if view_mode == "Shift Operations" else dept_df
        target_file = OPS_FILE if view_mode == "Shift Operations" else DEPT_FILE
        
        act = st.selectbox("Action", ["Change Status", "Add Person"])
        
        if act == "Change Status":
            if view_mode == "Shift Operations":
                u = st.selectbox("Unit", working_df['Unit'].unique())
                d = st.selectbox("Desk", working_df[working_df['Unit']==u]['Desk'].unique())
                p_list = working_df[(working_df['Unit']==u)&(working_df['Desk']==d)]
            else:
                dept = st.selectbox("Department", working_df['Department'].unique())
                p_list = working_df[working_df['Department']==dept]
            
            p = st.selectbox("Person", p_list['Staff_Name'].unique())
            s = st.selectbox("New Status", ["Active", "Transferred", "VACANCY"])
            
            if st.button("Update"):
                idx = p_list[p_list['Staff_Name']==p].index[0]
                working_df.at[idx,'Status'] = s
                if s=='VACANCY': working_df.at[idx,'Staff_Name']="VACANT"
                save_local(working_df, target_file)
                update_github(working_df, target_file)
                st.success("Updated!")
                st.rerun()

# Sidebar PDF Button
with st.sidebar:
    st.title("Report")
    if st.button("📄 Generate PDF"):
        with st.spinner("Generating..."):
            pdf_bytes = generate_pdf_report_lab(active_df, mode="Ops" if view_mode=="Shift Operations" else "Dept")
            st.download_button("⬇️ Download PDF", pdf_bytes, "Report.pdf", "application/pdf")
