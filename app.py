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
from reportlab.lib.units import inch

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'
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

# --- CHART & ICON GENERATORS ---
def create_dashboard_charts(df):
    op_df = df[df['Desk'] != 'Shift In-Charge']
    
    # 1. Pie Chart
    fig1, ax1 = plt.subplots(figsize=(4, 3))
    status_counts = op_df['Status'].value_counts()
    colors_map = {'VACANCY':'#D32F2F', 'Transferred':'#F57C00', 'Active':'#388E3C', 'Long Leave':'#555'}
    pie_cols = [colors_map.get(x, '#999') for x in status_counts.index]
    ax1.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', colors=pie_cols, startangle=90)
    ax1.set_title('Overall Status', fontsize=10, fontweight='bold')
    
    # 2. Bar Chart
    gaps = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
    if not gaps.empty:
        gap_counts = gaps.groupby(['Unit', 'Status']).size().unstack(fill_value=0)
        fig2, ax2 = plt.subplots(figsize=(5, 3))
        gap_counts.plot(kind='bar', stacked=False, color=[colors_map.get(x, 'red') for x in gap_counts.columns], ax=ax2)
        ax2.set_title('Critical Gaps', fontsize=10, fontweight='bold')
        ax2.tick_params(axis='x', rotation=0)
        ax2.legend(fontsize=8)
        plt.tight_layout()
    else:
        fig2, ax2 = plt.subplots(figsize=(5, 3))
        ax2.text(0.5, 0.5, "No Critical Gaps", ha='center', va='center')
        ax2.axis('off')

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
def generate_pdf_report_lab(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    # 1. Header
    story.append(Paragraph("MAHAGENCO Parli TPS - Operation Shift Report", styles['Title']))
    story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 15))

    # 2. Charts & Metrics
    chart1, chart2 = create_dashboard_charts(df)
    img1 = Image(chart1, width=200, height=150)
    img2 = Image(chart2, width=250, height=150)
    
    # Metrics Text
    op_df = df[df['Desk'] != 'Shift In-Charge']
    vacant_count = len(op_df[op_df['Status']=='VACANCY'])
    trf_count = len(op_df[op_df['Status']=='Transferred'])
    
    # Layout Table for Charts
    chart_table = Table([[img1, img2]], colWidths=[250, 250])
    chart_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(chart_table)
    story.append(Spacer(1, 10))
    
    # Metrics Row
    m_style = ParagraphStyle('M', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10)
    m_text = f"<b>CRITICAL VACANCIES: <font color='red'>{vacant_count}</font></b>  |  <b>TRANSFERS: <font color='orange'>{trf_count}</font></b>"
    story.append(Paragraph(m_text, m_style))
    story.append(Spacer(1, 20))

    # 3. Main Roster Matrix
    units = sorted(df['Unit'].unique())
    desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
             'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
    
    data = [['Position'] + units]
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
    ]
    
    for desk in desks:
        row = [Paragraph(f"<b>{desk}</b>", styles['Normal'])]
        for u in units:
            matches = op_df[(op_df['Unit'] == u) & (op_df['Desk'] == desk)]
            cell = []
            if matches.empty:
                cell.append(Paragraph("-", styles['Normal']))
            else:
                for _, r in matches.iterrows():
                    nm = format_staff_name(r['Staff_Name'])
                    if r['Status'] == 'VACANCY':
                        sub_t = Table([[draw_red_cross(), Paragraph("<b>VACANT</b>", styles['Normal'])]], colWidths=[12, 70])
                        sub_t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
                        cell.append(sub_t)
                    elif r['Status'] == 'Transferred':
                        sub_t = Table([[draw_orange_flag(), Paragraph(f"<i>{nm}</i>", styles['Normal'])]], colWidths=[12, 70])
                        sub_t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
                        cell.append(sub_t)
                    else:
                        cell.append(Paragraph(nm, styles['Normal']))
            row.append(cell)
        data.append(row)

    main_table = Table(data, colWidths=[100, 130, 130, 130])
    main_table.setStyle(TableStyle(t_style))
    story.append(main_table)
    
    # 4. Legend
    story.append(Spacer(1, 10))
    leg_data = [[draw_red_cross(), "Vacancy (Shortage)", draw_orange_flag(), "Transferred (Risk)"]]
    leg_table = Table(leg_data, colWidths=[15, 120, 15, 120])
    leg_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(leg_table)
    
    # 5. NEW SECTION: VACANCY & TRANSFER SUMMARY LIST
    story.append(PageBreak())
    story.append(Paragraph("Vacancy & Transfer Summary List", styles['Heading2']))
    story.append(Spacer(1, 10))
    
    # Filter for list
    summary_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])].copy()
    
    if not summary_df.empty:
        # Sort for readability
        summary_df = summary_df.sort_values(by=['Unit', 'Status'])
        
        # Summary Table Header
        sum_data = [['Unit', 'Desk', 'Staff Name / Status', 'Category']]
        
        for _, r in summary_df.iterrows():
            # Clean name
            nm = format_staff_name(r['Staff_Name'])
            status_txt = "SHORTAGE" if r['Status'] == 'VACANCY' else "TRANSFER"
            color_txt = colors.red if r['Status'] == 'VACANCY' else colors.orange
            
            # Row
            row = [
                r['Unit'],
                r['Desk'],
                Paragraph(f"<b>{nm}</b>", styles['Normal']),
                Paragraph(f"<b><font color='{color_txt}'>{status_txt}</font></b>", styles['Normal'])
            ]
            sum_data.append(row)
            
        sum_table = Table(sum_data, colWidths=[60, 150, 180, 100])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#34495e')), # Dark Header
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]), # Alternating rows
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(sum_table)
    else:
        story.append(Paragraph("No active vacancies or transfers reported.", styles['Normal']))

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

# ... (Search and Admin tabs preserved) ...
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
        elif act == "Transfer":
            c1, c2 = st.columns(2)
            u1 = c1.selectbox("From U", df['Unit'].unique())
            d1 = c1.selectbox("From D", df[df['Unit']==u1]['Desk'].unique())
            p = c1.selectbox("Per", df[(df['Unit']==u1)&(df['Desk']==d1)]['Staff_Name'].unique())
            u2 = c2.selectbox("To U", df['Unit'].unique())
            d2 = c2.selectbox("To D", df[df['Unit']==u2]['Desk'].unique())
            if st.button("Trf"):
                src = df[(df['Unit']==u1)&(df['Desk']==d1)&(df['Staff_Name']==p)].index[0]
                tgt = df[(df['Unit']==u2)&(df['Desk']==d2)&(df['Status']=='VACANCY')]
                if not tgt.empty:
                    df.at[tgt.index[0],'Staff_Name']=p; df.at[tgt.index[0],'Status']='Active'
                else:
                    df = pd.concat([df, pd.DataFrame([{"Unit":u2,"Desk":d2,"Staff_Name":p,"Status":"Active"}])], ignore_index=True)
                df.at[src,'Staff_Name']="VACANT"; df.at[src,'Status']="VACANCY"
                save_local(df); update_github(df); st.rerun()
