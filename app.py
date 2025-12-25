import streamlit as st
import pandas as pd
import plotly.express as px
import re
from github import Github
import io

# --- REPORTLAB IMPORTS (For Vector PDF) ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Line, Polygon
from reportlab.graphics import renderPDF

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #0E1117; border: 1px solid #30333F; border-radius: 10px; padding: 15px; text-align: center; }
    /* Webpage Badges */
    .badge-vacant { background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .badge-transfer { background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .badge-active { background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.85em; display: inline-block; margin-bottom: 2px;}
    .stButton>button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'admin_logged_in' not in st.session_state: st.session_state.admin_logged_in = False

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
    if match: return f"{clean[:match.start()].strip()} ({match.group(1)})"
    return clean

# --- VECTOR ICON GENERATORS (Crisp Printing) ---
def draw_red_cross():
    """Draws a vector Red X"""
    d = Drawing(10, 10)
    # Thick Red X
    d.add(Line(1, 1, 9, 9, strokeColor=colors.red, strokeWidth=2))
    d.add(Line(1, 9, 9, 1, strokeColor=colors.red, strokeWidth=2))
    return d

def draw_orange_flag():
    """Draws a vector Orange Flag"""
    d = Drawing(10, 10)
    # Pole
    d.add(Line(2, 0, 2, 10, strokeColor=colors.black, strokeWidth=1))
    # Flag Triangle (Filled)
    d.add(Polygon([2, 10, 9, 7, 2, 4], fillColor=colors.orange, strokeWidth=0))
    return d

# --- PDF ENGINE ---
def generate_pdf_report_lab(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    # 1. Header
    story.append(Paragraph("MAHAGENCO Parli TPS - Operation Shift Report", styles['Title']))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 15))

    # 2. Executive Metrics Table (Simple & Clean)
    op_df = df[df['Desk'] != 'Shift In-Charge']
    active = len(op_df[op_df['Status']=='Active'])
    vacant = len(op_df[op_df['Status']=='VACANCY'])
    transferred = len(op_df[op_df['Status']=='Transferred'])
    
    metric_data = [
        [f"Active Staff: {active}", f"CRITICAL VACANCIES: {vacant}", f"Transfers: {transferred}"]
    ]
    t_metrics = Table(metric_data, colWidths=[150, 180, 150])
    t_metrics.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke),
        ('BOX', (0,0), (-1,-1), 1, colors.grey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TEXTCOLOR', (1,0), (1,0), colors.red),
        ('FONTNAME', (1,0), (1,0), 'Helvetica-Bold'),
    ]))
    story.append(t_metrics)
    story.append(Spacer(1, 20))

    # 3. Main Roster Matrix
    units = sorted(df['Unit'].unique())
    desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
             'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
    
    # Header Row
    data = [['Position'] + units]
    
    # Base Styles
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
    ]
    
    for row_idx, desk in enumerate(desks, 1):
        # Desk Column (Bold)
        row = [Paragraph(f"<b>{desk}</b>", styles['Normal'])]
        
        for col_idx, u in enumerate(units, 1):
            matches = op_df[(op_df['Unit'] == u) & (op_df['Desk'] == desk)]
            cell_content = []
            
            if matches.empty:
                cell_content.append(Paragraph("-", styles['Normal']))
            else:
                for _, r in matches.iterrows():
                    nm = format_staff_name(r['Staff_Name'])
                    
                    if r['Status'] == 'VACANCY':
                        # Insert VECTOR drawing + Bold Text
                        icon = draw_red_cross()
                        # Table inside cell to align Icon and Text
                        sub_t = Table([[icon, Paragraph("<b>VACANT</b>", styles['Normal'])]], colWidths=[12, 70])
                        sub_t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
                        cell_content.append(sub_t)
                    
                    elif r['Status'] == 'Transferred':
                        # Insert VECTOR drawing + Italic Text
                        icon = draw_orange_flag()
                        sub_t = Table([[icon, Paragraph(f"<i>{nm}</i>", styles['Normal'])]], colWidths=[12, 70])
                        sub_t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
                        cell_content.append(sub_t)
                    
                    else:
                        # Standard Text
                        cell_content.append(Paragraph(nm, styles['Normal']))
            
            row.append(cell_content)
        data.append(row)

    # Build Table
    main_table = Table(data, colWidths=[100, 130, 130, 130])
    main_table.setStyle(TableStyle(t_style))
    story.append(main_table)
    
    # 4. Legend (Vector Icons in Legend too!)
    story.append(Spacer(1, 10))
    leg_cross = draw_red_cross()
    leg_flag = draw_orange_flag()
    leg_data = [[leg_cross, "Vacancy (Action Required)", leg_flag, "Transferred (Replacement Needed)"]]
    leg_table = Table(leg_data, colWidths=[15, 150, 15, 200])
    leg_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(leg_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/8/82/Mahagenco_Logo.png/220px-Mahagenco_Logo.png", width=100)
    st.title("Parli TPS Ops")
    search_term = st.text_input("Search Staff")
    if search_term and not df.empty:
        res = df[df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            for _, r in res.iterrows():
                st.markdown(f"**{format_staff_name(r['Staff_Name'])}** ({r['Unit']})")
        else: st.warning("No match")
    
    st.divider()
    if not df.empty:
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📥 CSV", csv_buffer, "data.csv")
        if st.button("📄 PDF Report"):
            with st.spinner("Generating High-Res PDF..."):
                try:
                    pdf_bytes = generate_pdf_report_lab(df)
                    st.download_button("⬇️ Download PDF", pdf_bytes, "Report.pdf", "application/pdf")
                except Exception as e:
                    st.error(f"Error: {e}")

# --- MAIN PAGE ---
st.title("⚡ Operation Staff Dashboard")
tab1, tab2, tab3 = st.tabs(["Overview", "Search", "Admin"])

with tab1:
    # 1. WEBPAGE: Colorful Badges (As requested)
    op_df = df[df['Desk'] != 'Shift In-Charge']
    
    def agg_staff_html(x):
        html = []
        for _, row in x.iterrows():
            name = format_staff_name(row['Staff_Name'])
            if row['Status'] == 'VACANCY': 
                html.append(f'<div class="badge-vacant">🔴 VACANT</div>')
            elif row['Status'] == 'Transferred': 
                html.append(f'<div class="badge-transfer">🟠 {name}</div>')
            else: 
                html.append(f'<div class="badge-active">👤 {name}</div>')
        return "".join(html)

    # Render Table
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

# ... (Standard Search/Admin tabs preserved) ...
with tab2:
    st.info("Select Unit and Desk to view details.")
    if not df.empty:
        u = st.selectbox("Unit", df['Unit'].unique())
        d = st.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
        sub = df[(df['Unit']==u) & (df['Desk']==d)]
        for _, r in sub.iterrows():
            st.write(f"- {format_staff_name(r['Staff_Name'])} ({r['Status']})")

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
        st.write("Use tools to update staff.")
        act = st.selectbox("Action", ["Add", "Transfer", "Status"])
        if act == "Status":
            u = st.selectbox("U", df['Unit'].unique())
            d = st.selectbox("D", df[df['Unit']==u]['Desk'].unique())
            p = st.selectbox("P", df[(df['Unit']==u)&(df['Desk']==d)]['Staff_Name'].unique())
            s = st.selectbox("S", ["Active", "Transferred", "VACANCY"])
            if st.button("Upd"):
                idx = df[(df['Unit']==u)&(df['Desk']==d)&(df['Staff_Name']==p)].index[0]
                df.at[idx,'Status'] = s
                if s=='VACANCY': df.at[idx,'Staff_Name']="VACANT"
                save_local(df); update_github(df); st.rerun()
