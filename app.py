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
from reportlab.graphics.shapes import Drawing, Line, Polygon

# --- CONFIGURATION & CONSTANTS ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")

OPS_FILE = 'stitched_staffing_data.csv'
DEPT_FILE = 'departmental_staffing_data.csv'
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

VIEW_OPS = "PCR Shift Operation (Main Plant)"
VIEW_DEPT = "Departmental Staff"

DESK_ORDER = [
    'PCR In-Charge',
    'Turbine Control Desk',
    'Boiler Control Desk',
    'Drum Level Desk',
    'Boiler API (BAPI)',
    'Turbine API (TAPI)'
]

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

    /* Flashcard / Play Card Styles */
    .desk-header {
        background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
        color: #f8fafc;
        padding: 8px 12px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 8px;
        border-left: 4px solid #38bdf8;
    }
    .playcard {
        padding: 8px 10px;
        border-radius: 8px;
        margin-bottom: 4px;
        font-size: 0.9rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .playcard-active {
        background-color: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-left: 5px solid #10b981;
    }
    .playcard-transfer {
        background-color: rgba(245, 158, 11, 0.15);
        border: 1px solid rgba(245, 158, 11, 0.5);
        border-left: 5px solid #f59e0b;
    }
    .playcard-vacant {
        background-color: rgba(239, 68, 68, 0.15);
        border: 1px dashed rgba(239, 68, 68, 0.6);
        border-left: 5px solid #ef4444;
    }
    .desg-pill {
        background-color: rgba(255, 255, 255, 0.12);
        padding: 1px 6px;
        border-radius: 4px;
        font-size: 0.78em;
        margin-left: 6px;
        color: #cbd5e1;
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'active_edit_card' not in st.session_state:
    st.session_state.active_edit_card = None
if 'active_add_box' not in st.session_state:
    st.session_state.active_add_box = None
if 'dashboard_card_edit' not in st.session_state:
    st.session_state.dashboard_card_edit = False

# --- DATA FUNCTIONS ---
def update_github(df, filename):
    try:
        token = st.secrets["github"]["token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(filename)
            repo.update_file(contents.path, f"Admin Update {filename}", df.to_csv(index=False), contents.sha)
        except Exception:
            repo.create_file(filename, "Initial Commit", df.to_csv(index=False))
        return True
    except Exception as e:
        st.error(f"GitHub Sync Error: {e}")
        return False

@st.cache_data(ttl=1)
def load_data(filename):
    try:
        df = pd.read_csv(filename)
        if filename == OPS_FILE and 'Desk' not in df.columns:
            return pd.DataFrame()
        if 'Designation' not in df.columns:
            df['Designation'] = ''
        if 'Status' not in df.columns:
            df['Status'] = 'Active'
        if 'Action_Required' not in df.columns:
            df['Action_Required'] = ''
        return df.fillna("")
    except Exception:
        return pd.DataFrame()

def save_and_sync(df, filename):
    df.to_csv(filename, index=False)
    st.cache_data.clear()
    update_github(df, filename)

def format_staff_name(raw_name, desg=""):
    if "VACANT" in str(raw_name).upper():
        return "VACANT"
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', str(raw_name), flags=re.IGNORECASE).strip()
    if desg and str(desg).strip() and str(desg).lower() not in clean.lower():
        clean = f"{clean} ({desg})"
    elif not desg:
        pattern = r'\s+(JE|AE|DY\.? ?EE|ADD\.? ?EE|AD\.? ?EE|EE)\b'
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            clean = f"{clean[:match.start()].strip()} ({match.group(1)})"
    return clean

def get_rank_level(desg):
    d = str(desg).upper().replace('.', '').strip()
    if 'EXECUTIVE' in d or 'EE' in d:
        if 'ADD' in d or 'AD' in d:
            return 2
        if 'DY' in d:
            return 3
        if d == 'EE' or d == 'EXECUTIVE ENGINEER':
            return 1
    if 'AE' in d or 'ASSISTANT' in d:
        return 4
    if 'JE' in d or 'JUNIOR' in d:
        return 5
    return 6

# --- GRAPHIC HELPERS ---
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

# --- UNIVERSAL METRICS HELPER ---
def calculate_metrics(df):
    if df.empty:
        return 0, 0, pd.Series()
    staff_only = df[df['Staff_Name'].str.contains("VACANT", case=False) == False].copy()
    staff_only['Staff_Name'] = staff_only['Staff_Name'].astype(str).str.strip()
    staff_only['Status_Rank'] = staff_only['Status'].apply(lambda x: 2 if 'Transferred' in str(x) else 1)
    staff_only = staff_only.sort_values(by=['Staff_Name', 'Status_Rank'], ascending=[True, False])
    unique_staff = staff_only.drop_duplicates(subset=['Staff_Name'], keep='first')
    transferred = len(unique_staff[unique_staff['Status'] == 'Transferred'])
    vacant = len(df[df['Status'] == 'VACANCY'])
    status_counts = unique_staff['Status'].value_counts()
    if vacant > 0:
        status_counts['VACANCY'] = vacant
    return vacant, transferred, status_counts

def get_global_metrics(ops_df, dept_df, scope="Global"):
    dfs = []
    if not ops_df.empty and scope in ["Global", "Ops"]:
        clean_ops = ops_df[ops_df['Desk'] != 'Shift In-Charge'][['Staff_Name', 'Status']].copy()
        dfs.append(clean_ops)
    if not dept_df.empty:
        if scope == "Global":
            dfs.append(dept_df[['Staff_Name', 'Status']])
        elif scope == "Ops":
            sic = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)][['Staff_Name', 'Status']]
            dfs.append(sic)
        elif scope == "Dept":
            dfs.append(dept_df[['Staff_Name', 'Status']])
    if not dfs:
        return 0, 0, pd.Series()
    combined = pd.concat(dfs)
    return calculate_metrics(combined)

# --- PDF ENGINE ---
def generate_combined_pdf(ops_df, dept_df, report_type="Summary"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading3']
    normal_style = styles['Normal']

    if report_type == "Single Page Op Vacancy":
        story.append(Paragraph("MAHAGENCO Parli TPS - Operation Vacancy Overview", title_style))
        story.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", normal_style))
        story.append(Spacer(1, 15))

        sic_df = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)]
        sic_anomalies = sic_df[sic_df['Status'].isin(['VACANCY', 'Transferred'])] if not sic_df.empty else pd.DataFrame()

        if not sic_anomalies.empty:
            story.append(Paragraph("⚠️ Shift In-Charge (Attention Required)", heading_style))
            sic_data = [['Unit', 'Name', 'Status']]
            for _, r in sic_anomalies.iterrows():
                unit = "Unit 6 & 7" if "U6&7" in r['Department'] else "Unit 8"
                nm = format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                st_txt = "TRANSFERRED" if r['Status'] == 'Transferred' else "VACANT"
                sic_data.append([unit, nm, st_txt])

            t_sic = Table(sic_data, colWidths=[150, 300, 150])
            t_sic.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.red),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('BACKGROUND', (0,1), (-1,-1), colors.white),
                ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
            ]))
            story.append(t_sic)
            story.append(Spacer(1, 15))

        if not ops_df.empty:
            story.append(Paragraph("Shift Operations Roster", heading_style))
            units = sorted(ops_df['Unit'].unique())
            main_data = [['Position'] + units]

            for desk in DESK_ORDER:
                row = [desk]
                for u in units:
                    matches = ops_df[(ops_df['Unit'] == u) & (ops_df['Desk'] == desk)]
                    if matches.empty:
                        row.append("-")
                    else:
                        cell_content = []
                        for _, r in matches.iterrows():
                            nm = format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                            if r['Status'] == 'VACANCY':
                                cell_content.append(Table([[draw_red_cross(), Paragraph("<b>VACANT</b>", normal_style)]], colWidths=[15, 80]))
                            elif r['Status'] == 'Transferred':
                                cell_content.append(Table([[draw_orange_flag(), Paragraph(f"<i>{nm}</i>", normal_style)]], colWidths=[15, 80]))
                            else:
                                cell_content.append(Paragraph(nm, normal_style))
                        row.append(cell_content)
                main_data.append(row)

            t_main = Table(main_data, colWidths=[120, 180, 180, 180])
            t_main.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('FONTSIZE', (0,0), (-1,-1), 8)
            ]))
            story.append(t_main)
            story.append(Spacer(1, 15))

        story.append(Paragraph("Detailed Vacancy & Transfer List", heading_style))
        op_issues = ops_df[ops_df['Status'].isin(['VACANCY', 'Transferred'])].sort_values(['Unit', 'Desk'])

        list_data = [['Unit', 'Desk', 'Name', 'Status']]
        for _, r in op_issues.iterrows():
            nm = format_staff_name(r['Staff_Name'], r.get('Designation', ''))
            list_data.append([r['Unit'], r['Desk'], nm, r['Status']])

        if len(list_data) > 1:
            t_list = Table(list_data, colWidths=[80, 200, 250, 120])
            t_list.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4b5563')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white])
            ]))
            story.append(t_list)
        else:
            story.append(Paragraph("No other vacancies or transfers found in Shift Operations.", normal_style))

    else:
        story.append(Paragraph("MAHAGENCO Parli TPS - Consolidated Staffing Report", title_style))
        story.append(Paragraph(f"Type: {report_type} | Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
        story.append(Spacer(1, 20))

        v_total, t_total, _ = get_global_metrics(ops_df, dept_df, "Global")
        v_ops, t_ops, _ = get_global_metrics(ops_df, dept_df, "Ops")
        v_dept, t_dept, _ = get_global_metrics(pd.DataFrame(), dept_df, "Dept")

        summary_data = [
            ['Section', 'Total Vacancies', 'Total Transferred'],
            ['Shift Operations (Inc. In-Charge)', v_ops, t_ops],
            ['Departmental Staff', v_dept, t_dept],
            ['TOTAL PLANT', v_total, t_total]
        ]
        t_sum = Table(summary_data, colWidths=[200, 100, 100])
        t_sum.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
            ('ALIGN', (0,0), (-1,-1), 'CENTER')
        ]))
        story.append(t_sum)
        story.append(Spacer(1, 30))

        story.append(Paragraph("1. Shift Operations (Main Plant)", styles['Heading2']))

        sic_df = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)] if not dept_df.empty else pd.DataFrame()
        if not sic_df.empty:
            story.append(Paragraph("Shift In-Charge (EE)", heading_style))
            u67 = ", ".join(sic_df[sic_df['Department'] == 'Shift In-Charge (U6&7)']['Staff_Name'].unique())
            u8 = ", ".join(sic_df[sic_df['Department'] == 'Shift In-Charge (U8)']['Staff_Name'].unique())
            sic_data = [['Unit 6 & 7 (Common)', u67], ['Unit 8', u8]]
            t_sic = Table(sic_data, colWidths=[150, 450])
            t_sic.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (0,-1), colors.lightgrey)]))
            story.append(t_sic)
            story.append(Spacer(1, 10))

        if report_type == "Summary (Numbers)":
            agg_data = [['Unit', 'Active Staff', 'Vacant', 'Transferred']]
            if not ops_df.empty:
                groups = ops_df.groupby('Unit')
                for name, group in groups:
                    v, t, s = calculate_metrics(group)
                    agg_data.append([name, s.get('Active', 0), v, t])
            t_agg = Table(agg_data, colWidths=[150, 100, 80, 100])
            t_agg.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
            story.append(t_agg)
        else:
            if not ops_df.empty:
                units = sorted(ops_df['Unit'].unique())
                main_data = [['Position'] + units]
                for desk in DESK_ORDER:
                    row = [desk]
                    for u in units:
                        matches = ops_df[(ops_df['Unit'] == u) & (ops_df['Desk'] == desk)]
                        if matches.empty:
                            row.append("-")
                        else:
                            names = []
                            for _, r in matches.iterrows():
                                nm = format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                                if r['Status'] == 'VACANCY':
                                    nm = "VACANT"
                                elif r['Status'] == 'Transferred':
                                    nm = f"{nm} (Trf)"
                                names.append(nm)
                            row.append("\n".join(names))
                    main_data.append(row)
                t_main = Table(main_data, colWidths=[120, 180, 180, 180])
                t_main.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                    ('FONTSIZE', (0,0), (-1,-1), 8)
                ]))
                story.append(t_main)

        story.append(PageBreak())
        story.append(Paragraph("2. Departmental Staff", styles['Heading2']))

        if not dept_df.empty:
            if report_type == "Summary (Numbers)":
                agg_data = [['Department', 'Active Staff', 'Vacant', 'Transferred']]
                groups = dept_df.groupby('Department')
                for name, group in groups:
                    v, t, s = calculate_metrics(group)
                    agg_data.append([name, s.get('Active', 0), v, t])
                t_agg = Table(agg_data, colWidths=[250, 100, 80, 100])
                t_agg.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
                story.append(t_agg)
            else:
                depts = sorted(dept_df['Department'].unique())
                for d in depts:
                    group = dept_df[dept_df['Department'] == d]
                    if group.empty:
                        continue
                    story.append(Paragraph(f"{d} ({len(group)})", heading_style))
                    d_data = [['Name', 'Designation', 'Status']]
                    group = group.copy()
                    group['Rank'] = group['Designation'].apply(get_rank_level)
                    group = group.sort_values('Rank')
                    for _, r in group.iterrows():
                        d_data.append([format_staff_name(r['Staff_Name']), str(r['Designation']), r['Status']])
                    t_dept = Table(d_data, colWidths=[250, 150, 100])
                    t_dept.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
                    story.append(t_dept)
                    story.append(Spacer(1, 15))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ==============================================================================
# INTERACTIVE PLAY CARD (FLASHCARD) ENGINE
# ==============================================================================
def render_playcard(df, idx, is_ops, target_file, key_prefix="card"):
    """
    Renders a single employee / vacancy Play Card.
    Clicking '✏️' flips/expands the card in-place with full admin actions:
    - Edit Name, Designation, SAP ID, Status (Active / Transferred / VACANCY)
    - Fill Vacancy directly
    - Transfer / Swap with another Unit+Desk or Department
    - Vacate or Delete slot
    """
    row = df.loc[idx]
    status = str(row.get('Status', 'Active'))
    raw_name = str(row.get('Staff_Name', '')).strip()
    desg = str(row.get('Designation', '')).strip()
    sap_id = str(row.get('SAP_ID', '')).strip()
    is_vacant = (status == 'VACANCY') or ('VACANT' in raw_name.upper())

    card_uid = f"{key_prefix}_{'ops' if is_ops else 'dept'}_{idx}"
    is_editing = (st.session_state.active_edit_card == card_uid)

    if is_vacant:
        css_class = "playcard-vacant"
        icon = "🔴"
        title_html = "<b>VACANT SLOT</b>"
    elif status == 'Transferred':
        css_class = "playcard-transfer"
        icon = "🟠"
        desg_html = f'<span class="desg-pill">{desg}</span>' if desg else ""
        title_html = f"<b>{raw_name}</b>{desg_html} <small>(Trf)</small>"
    else:
        css_class = "playcard-active"
        icon = "🟢"
        desg_html = f'<span class="desg-pill">{desg}</span>' if desg else ""
        title_html = f"<b>{raw_name}</b>{desg_html}"

    # --- FRONT OF PLAY CARD ---
    c_card, c_btn = st.columns([4.2, 1.2])
    with c_card:
        st.markdown(
            f'<div class="playcard {css_class}"><span>{icon} {title_html}</span></div>',
            unsafe_allow_html=True
        )
    with c_btn:
        btn_label = "✖️" if is_editing else ("➕ Fill" if is_vacant else "✏️")
        if st.button(btn_label, key=f"btn_{card_uid}", help="Edit this Play Card"):
            st.session_state.active_edit_card = None if is_editing else card_uid
            st.rerun()

    # --- BACK OF PLAY CARD (INLINE EDITOR WHEN CLICKED) ---
    if is_editing:
        with st.container(border=True):
            loc_str = f"{row['Unit']} | {row['Desk']}" if is_ops else str(row['Department'])
            st.caption(f"📍 Editing Slot: **{loc_str}**")

            edit_tab1, edit_tab2 = st.tabs(["✏️ Edit / Status", "🔄 Transfer / Swap"])

            with edit_tab1:
                new_name = st.text_input(
                    "Staff Name",
                    value="" if is_vacant else raw_name,
                    placeholder="Enter staff name...",
                    key=f"nm_{card_uid}"
                )
                ec1, ec2 = st.columns(2)
                new_desg = ec1.text_input(
                    "Designation",
                    value=desg,
                    placeholder="e.g. AE, Dy.EE, JE",
                    key=f"dg_{card_uid}"
                )
                status_options = ["Active", "Transferred", "VACANCY"]
                default_stat_idx = status_options.index(status) if status in status_options else 0
                new_status = ec2.selectbox(
                    "Status",
                    status_options,
                    index=0 if (is_vacant and new_name.strip()) else default_stat_idx,
                    key=f"st_{card_uid}"
                )

                new_sap = sap_id
                if not is_ops:
                    new_sap = st.text_input("SAP ID (Optional)", value=sap_id, key=f"sap_{card_uid}")

                b1, b2, b3 = st.columns(3)
                if b1.button("💾 Save", key=f"sv_{card_uid}", type="primary"):
                    if new_status == "VACANCY" or not new_name.strip():
                        df.at[idx, 'Staff_Name'] = "VACANT"
                        df.at[idx, 'Status'] = "VACANCY"
                        df.at[idx, 'Designation'] = new_desg.strip()
                    else:
                        df.at[idx, 'Staff_Name'] = new_name.strip()
                        df.at[idx, 'Designation'] = new_desg.strip()
                        df.at[idx, 'Status'] = "Active" if is_vacant else new_status
                    if not is_ops and 'SAP_ID' in df.columns:
                        df.at[idx, 'SAP_ID'] = new_sap.strip()
                    save_and_sync(df, target_file)
                    st.session_state.active_edit_card = None
                    st.toast("Saved changes!", icon="✅")
                    st.rerun()

                if not is_vacant:
                    if status != "Transferred":
                        if b2.button("🟠 Flag Trf", key=f"trf_{card_uid}", help="Mark as Transferred (pending exit)"):
                            df.at[idx, 'Status'] = "Transferred"
                            save_and_sync(df, target_file)
                            st.session_state.active_edit_card = None
                            st.toast(f"{raw_name} flagged as Transferred.", icon="🟠")
                            st.rerun()
                    else:
                        if b2.button("🟢 Set Active", key=f"act_{card_uid}"):
                            df.at[idx, 'Status'] = "Active"
                            save_and_sync(df, target_file)
                            st.session_state.active_edit_card = None
                            st.rerun()

                    if b3.button("🔴 Vacate", key=f"vac_{card_uid}", help="Person left - make slot VACANT"):
                        df.at[idx, 'Staff_Name'] = "VACANT"
                        df.at[idx, 'Status'] = "VACANCY"
                        save_and_sync(df, target_file)
                        st.session_state.active_edit_card = None
                        st.toast("Slot marked VACANT.", icon="🔴")
                        st.rerun()
                else:
                    if b3.button("🗑️ Delete Slot", key=f"del_{card_uid}", help="Remove this vacant slot permanently"):
                        df = df.drop(index=idx).reset_index(drop=True)
                        save_and_sync(df, target_file)
                        st.session_state.active_edit_card = None
                        st.toast("Slot deleted.", icon="🗑️")
                        st.rerun()

                if not is_vacant:
                    if st.button("🗑️ Delete Row Entirely (Remove Slot)", key=f"delrow_{card_uid}"):
                        df = df.drop(index=idx).reset_index(drop=True)
                        save_and_sync(df, target_file)
                        st.session_state.active_edit_card = None
                        st.toast("Row removed.", icon="🗑️")
                        st.rerun()

            with edit_tab2:
                if is_vacant:
                    st.info("This slot is vacant. Use the '✏️ Edit / Status' tab to fill it with a name.")
                else:
                    if is_ops:
                        all_locs = sorted(df.apply(lambda r: f"{r['Unit']} | {r['Desk']}", axis=1).unique().tolist())
                    else:
                        all_locs = sorted(df['Department'].astype(str).unique().tolist())

                    other_locs = [l for l in all_locs if l != loc_str]
                    if not other_locs:
                        st.info("No other locations available.")
                    else:
                        dest_loc = st.selectbox("Transfer To", other_locs, key=f"dest_{card_uid}")
                        if is_ops:
                            d_unit, d_desk = dest_loc.split(" | ", 1)
                            dest_rows = df[(df['Unit'] == d_unit) & (df['Desk'] == d_desk)]
                        else:
                            dest_rows = df[df['Department'] == dest_loc]

                        dest_vac = dest_rows[dest_rows['Status'] == 'VACANCY']
                        dest_occ = dest_rows[(dest_rows['Status'] != 'VACANCY') & (~dest_rows['Staff_Name'].str.upper().str.contains("VACANT"))]

                        st.caption(f"**{dest_loc}** has {len(dest_occ)} staff and {len(dest_vac)} open vacancy(ies).")

                        t_modes = []
                        if not dest_vac.empty:
                            t_modes.append("Move into existing vacancy there")
                        if not dest_occ.empty:
                            t_modes.append("Swap places with someone there")
                        t_modes.append("Create a new slot there")

                        t_mode = st.radio("Transfer Mode", t_modes, key=f"tmode_{card_uid}")

                        swap_target_idx = None
                        replacement_nm = ""
                        if t_mode == "Swap places with someone there":
                            occ_options = {
                                f"{r['Staff_Name']} ({r.get('Designation', '')})": i
                                for i, r in dest_occ.iterrows()
                            }
                            chosen_swap = st.selectbox("Swap with", list(occ_options.keys()), key=f"swp_{card_uid}")
                            swap_target_idx = occ_options[chosen_swap]
                        else:
                            leave_opt = st.radio(
                                "Current slot after transfer:",
                                ["Leave VACANT", "Fill with replacement"],
                                horizontal=True,
                                key=f"lv_{card_uid}"
                            )
                            if leave_opt == "Fill with replacement":
                                replacement_nm = st.text_input("Replacement Name", key=f"rep_{card_uid}")

                        if st.button("🚀 Confirm Transfer", key=f"exec_trf_{card_uid}", type="primary"):
                            moved_data = {
                                "Staff_Name": raw_name,
                                "Designation": desg,
                                "Status": "Active"
                            }
                            if not is_ops and 'SAP_ID' in df.columns:
                                moved_data["SAP_ID"] = sap_id

                            if t_mode == "Move into existing vacancy there":
                                t_idx = dest_vac.index[0]
                                for k, v in moved_data.items():
                                    df.at[t_idx, k] = v
                                if replacement_nm.strip():
                                    df.at[idx, 'Staff_Name'] = replacement_nm.strip()
                                    df.at[idx, 'Status'] = "Active"
                                else:
                                    df.at[idx, 'Staff_Name'] = "VACANT"
                                    df.at[idx, 'Status'] = "VACANCY"

                            elif t_mode == "Swap places with someone there":
                                other_row = df.loc[swap_target_idx].copy()
                                df.at[swap_target_idx, 'Staff_Name'] = raw_name
                                df.at[swap_target_idx, 'Designation'] = desg
                                df.at[swap_target_idx, 'Status'] = "Active"

                                df.at[idx, 'Staff_Name'] = other_row['Staff_Name']
                                df.at[idx, 'Designation'] = other_row.get('Designation', '')
                                df.at[idx, 'Status'] = "Active"
                                if not is_ops and 'SAP_ID' in df.columns:
                                    df.at[swap_target_idx, 'SAP_ID'] = sap_id
                                    df.at[idx, 'SAP_ID'] = other_row.get('SAP_ID', '')

                            else:
                                if is_ops:
                                    d_unit, d_desk = dest_loc.split(" | ", 1)
                                    new_r = {
                                        "Unit": d_unit,
                                        "Desk": d_desk,
                                        "Staff_Name": raw_name,
                                        "Designation": desg,
                                        "Status": "Active",
                                        "Action_Required": ""
                                    }
                                else:
                                    new_r = {
                                        "Department": dest_loc,
                                        "Staff_Name": raw_name,
                                        "Designation": desg,
                                        "SAP_ID": sap_id,
                                        "Status": "Active",
                                        "Action_Required": ""
                                    }
                                if replacement_nm.strip():
                                    df.at[idx, 'Staff_Name'] = replacement_nm.strip()
                                    df.at[idx, 'Status'] = "Active"
                                else:
                                    df.at[idx, 'Staff_Name'] = "VACANT"
                                    df.at[idx, 'Status'] = "VACANCY"
                                df = pd.concat([df, pd.DataFrame([new_r])], ignore_index=True)

                            save_and_sync(df, target_file)
                            st.session_state.active_edit_card = None
                            st.toast(f"Transferred {raw_name} to {dest_loc}!", icon="🔄")
                            st.rerun()


def render_add_button_for_group(df, is_ops, target_file, unit_val="", desk_val="", dept_val="", key_prefix="add"):
    """Renders an inline '➕ Add Staff / Slot' button right inside a Desk or Department card."""
    box_uid = f"{key_prefix}_{unit_val}_{desk_val}_{dept_val}"
    is_open = (st.session_state.active_add_box == box_uid)

    if st.button("✖️ Cancel Add" if is_open else "➕ Add Staff / Slot", key=f"btn_{box_uid}"):
        st.session_state.active_add_box = None if is_open else box_uid
        st.rerun()

    if is_open:
        with st.container(border=True):
            st.caption(f"➕ Add to **{unit_val + ' - ' + desk_val if is_ops else dept_val}**")
            a_name = st.text_input("Full Name (or leave blank to add a VACANT slot)", key=f"anm_{box_uid}")
            ac1, ac2 = st.columns(2)
            a_desg = ac1.text_input("Designation", placeholder="AE / Dy.EE / JE / EE", key=f"adg_{box_uid}")
            a_mode = ac2.selectbox("Slot Action", ["Create New Slot", "Fill Existing Vacancy (if any)"], key=f"amd_{box_uid}")

            a_sap = ""
            if not is_ops:
                a_sap = st.text_input("SAP ID (Optional)", key=f"asap_{box_uid}")

            if st.button("✅ Add Now", key=f"asv_{box_uid}", type="primary"):
                final_name = a_name.strip() if a_name.strip() else "VACANT"
                final_status = "Active" if a_name.strip() else "VACANCY"

                filled_existing = False
                if a_mode == "Fill Existing Vacancy (if any)" and final_status == "Active":
                    if is_ops:
                        vac_matches = df[(df['Unit'] == unit_val) & (df['Desk'] == desk_val) & (df['Status'] == 'VACANCY')]
                    else:
                        vac_matches = df[(df['Department'] == dept_val) & (df['Status'] == 'VACANCY')]
                    if not vac_matches.empty:
                        v_idx = vac_matches.index[0]
                        df.at[v_idx, 'Staff_Name'] = final_name
                        df.at[v_idx, 'Designation'] = a_desg.strip()
                        df.at[v_idx, 'Status'] = "Active"
                        if not is_ops and 'SAP_ID' in df.columns:
                            df.at[v_idx, 'SAP_ID'] = a_sap.strip()
                        filled_existing = True

                if not filled_existing:
                    if is_ops:
                        new_row = {
                            "Unit": unit_val,
                            "Desk": desk_val,
                            "Staff_Name": final_name,
                            "Designation": a_desg.strip(),
                            "Status": final_status,
                            "Action_Required": ""
                        }
                    else:
                        new_row = {
                            "Department": dept_val,
                            "Staff_Name": final_name,
                            "Designation": a_desg.strip(),
                            "SAP_ID": a_sap.strip(),
                            "Status": final_status,
                            "Action_Required": ""
                        }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

                save_and_sync(df, target_file)
                st.session_state.active_add_box = None
                st.toast(f"Added {final_name}!", icon="✅")
                st.rerun()


def render_ops_playcard_board(ops_df, dept_df, filter_mode="All", search_query="", key_prefix="board"):
    """
    Renders the complete Operations Flashcard / Play Card Board:
    1. Shift In-Charge (EE) Play Cards (U6&7 and U8)
    2. Unit 6, Unit 7, Unit 8 Desk Play Cards side-by-side
    """
    # --- 1. SHIFT IN-CHARGE PLAY CARDS ---
    with st.expander("👨‍✈️ Shift In-Charge (EE) Play Cards (Click ✏️ to Edit)", expanded=True):
        sic_cols = st.columns(2)
        for idx_c, sic_dept_name in enumerate(["Shift In-Charge (U6&7)", "Shift In-Charge (U8)"]):
            with sic_cols[idx_c]:
                st.markdown(f'<div class="desk-header">👨‍✈️ {sic_dept_name}</div>', unsafe_allow_html=True)
                sic_rows = dept_df[dept_df['Department'] == sic_dept_name]
                if filter_mode == "🔴 Vacancies Only":
                    sic_rows = sic_rows[sic_rows['Status'] == 'VACANCY']
                elif filter_mode == "🟠 Transferred Only":
                    sic_rows = sic_rows[sic_rows['Status'] == 'Transferred']
                if search_query:
                    sic_rows = sic_rows[sic_rows['Staff_Name'].str.contains(search_query, case=False, na=False)]

                for r_idx in sic_rows.index:
                    render_playcard(dept_df, r_idx, is_ops=False, target_file=DEPT_FILE, key_prefix=f"{key_prefix}_sic")
                render_add_button_for_group(dept_df, is_ops=False, target_file=DEPT_FILE, dept_val=sic_dept_name, key_prefix=f"{key_prefix}_sicadd")

    st.divider()

    # --- 2. MAIN PLANT PCR DESK PLAY CARDS BY UNIT ---
    units = sorted(ops_df['Unit'].unique()) if not ops_df.empty else ["Unit 6", "Unit 7", "Unit 8"]
    all_desks = [d for d in DESK_ORDER if d in ops_df['Desk'].unique()]
    for extra_d in ops_df['Desk'].unique():
        if extra_d not in all_desks and extra_d != "Shift In-Charge":
            all_desks.append(extra_d)

    unit_filter = st.radio("View Units:", ["All Units (Side-by-Side)"] + units, horizontal=True, key=f"{key_prefix}_uf")
    display_units = units if unit_filter == "All Units (Side-by-Side)" else [unit_filter]

    for desk in all_desks:
        st.markdown(f"#### 🖥️ {desk}")
        u_cols = st.columns(len(display_units))
        for col_i, u in enumerate(display_units):
            with u_cols[col_i]:
                with st.container(border=True):
                    st.markdown(f'<div class="desk-header">{u} — {desk}</div>', unsafe_allow_html=True)
                    matches = ops_df[(ops_df['Unit'] == u) & (ops_df['Desk'] == desk)]

                    if filter_mode == "🔴 Vacancies Only":
                        matches = matches[matches['Status'] == 'VACANCY']
                    elif filter_mode == "🟠 Transferred Only":
                        matches = matches[matches['Status'] == 'Transferred']
                    if search_query:
                        matches = matches[
                            matches['Staff_Name'].str.contains(search_query, case=False, na=False) |
                            matches['Designation'].str.contains(search_query, case=False, na=False)
                        ]

                    if matches.empty:
                        st.caption("No matching slots.")
                    else:
                        for r_idx in matches.index:
                            render_playcard(ops_df, r_idx, is_ops=True, target_file=OPS_FILE, key_prefix=f"{key_prefix}_ops")

                    render_add_button_for_group(
                        ops_df, is_ops=True, target_file=OPS_FILE,
                        unit_val=u, desk_val=desk, key_prefix=f"{key_prefix}_opsadd"
                    )


def render_dept_playcard_board(dept_df, filter_mode="All", search_query="", key_prefix="deptboard"):
    """Renders Departmental Staff as Interactive Play Cards grouped by Department & Rank."""
    all_depts = sorted(dept_df['Department'].unique().tolist())
    sel_dept = st.selectbox("Select Department (or View All)", ["All Departments"] + all_depts, key=f"{key_prefix}_sel")

    target_depts = all_depts if sel_dept == "All Departments" else [sel_dept]

    for d_name in target_depts:
        group = dept_df[dept_df['Department'] == d_name].copy()
        if filter_mode == "🔴 Vacancies Only":
            group = group[group['Status'] == 'VACANCY']
        elif filter_mode == "🟠 Transferred Only":
            group = group[group['Status'] == 'Transferred']
        if search_query:
            group = group[
                group['Staff_Name'].str.contains(search_query, case=False, na=False) |
                group['Designation'].str.contains(search_query, case=False, na=False)
            ]

        if group.empty and (filter_mode != "All" or search_query):
            continue

        with st.expander(f"📂 {d_name} ({len(group)} shown)", expanded=(sel_dept != "All Departments" or bool(search_query))):
            group['Rank'] = group['Designation'].apply(get_rank_level)
            group = group.sort_values('Rank')

            cols = st.columns(2)
            for idx_item, r_idx in enumerate(group.index):
                with cols[idx_item % 2]:
                    render_playcard(dept_df, r_idx, is_ops=False, target_file=DEPT_FILE, key_prefix=f"{key_prefix}_d")

            st.markdown("---")
            render_add_button_for_group(
                dept_df, is_ops=False, target_file=DEPT_FILE,
                dept_val=d_name, key_prefix=f"{key_prefix}_dadd"
            )


# --- HEADER & NAVIGATION ---
st.title("⚡ Mahagenco Staffing Portal")

# Sidebar Controls
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("🔐 Quick Admin Access")
if not st.session_state.admin_logged_in:
    sb_pwd = st.sidebar.text_input("Admin Password", type="password", key="sb_pwd")
    if st.sidebar.button("Login as Admin"):
        if sb_pwd == "admin123":
            st.session_state.admin_logged_in = True
            st.session_state.dashboard_card_edit = True
            st.rerun()
        else:
            st.sidebar.error("Wrong password")
else:
    st.sidebar.success("🔓 Admin Logged In")
    st.session_state.dashboard_card_edit = st.sidebar.toggle(
        "🃏 Edit directly on Dashboard Cards",
        value=st.session_state.dashboard_card_edit
    )
    if st.sidebar.button("Logout Admin"):
        st.session_state.admin_logged_in = False
        st.session_state.dashboard_card_edit = False
        st.session_state.active_edit_card = None
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("Report Options")
report_type = st.sidebar.radio("PDF Type", ["Summary (Numbers)", "Detailed (Names)", "Single Page Op Vacancy"])

ops_df = load_data(OPS_FILE)
dept_df = load_data(DEPT_FILE)

if st.sidebar.button("📄 Generate PDF Report"):
    with st.spinner("Generating..."):
        if ops_df.empty and dept_df.empty:
            st.sidebar.error("No data available.")
        else:
            pdf_bytes = generate_combined_pdf(ops_df, dept_df, report_type)
            st.sidebar.download_button("⬇️ Download PDF", pdf_bytes, f"Report_{report_type.replace(' ','_')}.pdf", "application/pdf")

view_mode = st.radio("", [VIEW_OPS, VIEW_DEPT], horizontal=True, label_visibility="collapsed")
active_df = ops_df if view_mode == VIEW_OPS else dept_df

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Roster", "🔍 Search & Reports", "🛠️ Admin Play Cards"])

# ==============================================================================
# TAB 1: DASHBOARD & ROSTER
# ==============================================================================
with tab1:
    if view_mode == VIEW_OPS:
        if ops_df.empty:
            st.error("Data Missing for Shift Ops.")
        else:
            op_df = ops_df[ops_df['Desk'] != 'Shift In-Charge']
            vacant_count, transferred_count, status_counts = get_global_metrics(ops_df, dept_df, "Ops")

            c1, c2, c3 = st.columns([1, 1.5, 1.2])
            with c1:
                st.markdown("##### Staff Status")
                fig1 = px.pie(
                    values=status_counts.values, names=status_counts.index,
                    color=status_counts.index,
                    color_discrete_map={'VACANCY': '#ff4b4b', 'Transferred': '#ffa421', 'Active': '#00CC96'},
                    hole=0.4, height=350
                )
                st.plotly_chart(fig1, use_container_width=True)
            with c2:
                st.markdown("##### Gaps by Unit")
                gaps_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
                if not gaps_df.empty:
                    fig2 = px.histogram(
                        gaps_df, x="Unit", color="Status", barmode="group",
                        color_discrete_map={'VACANCY': '#ff4b4b', 'Transferred': '#ffa421'},
                        text_auto=True, height=350
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.success("No Manpower Gaps!")
            with c3:
                st.markdown("##### Metrics")
                m1, m2 = st.columns(2)
                m1.metric("Shortage", vacant_count)
                m2.metric("Transferred", transferred_count)

            # If Admin toggled Direct Play Card Editing on Dashboard:
            if st.session_state.admin_logged_in and st.session_state.dashboard_card_edit:
                st.info("🃏 **Interactive Play Card Edit Mode is ON.** Click `✏️` on any card below to edit names, status, or transfer staff.")
                render_ops_playcard_board(ops_df, dept_df, key_prefix="dash")
            else:
                st.subheader("👨‍✈️ Shift In-Charge (EE)")
                sic_dept = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)]
                if not sic_dept.empty:
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
                        sic_data.append({"Unit 6 & 7 (Common Pool)": f"{s67_icon} {n67}", "Unit 8": f"{s8_icon} {n8}"})
                    st.dataframe(pd.DataFrame(sic_data), use_container_width=True, hide_index=True)

                st.divider()

                def agg_staff_html(x):
                    html = []
                    for _, row in x.iterrows():
                        name = format_staff_name(row['Staff_Name'], row.get('Designation', ''))
                        if row['Status'] == 'VACANCY':
                            html.append('<div class="badge-vacant">🔴 VACANT</div>')
                        elif row['Status'] == 'Transferred':
                            html.append(f'<div class="badge-transfer">🟠 {name}</div>')
                        else:
                            html.append(f'<div class="badge-active">👤 {name}</div>')
                    return "".join(html)

                units = sorted(op_df['Unit'].unique())
                table_data = []
                for desk in DESK_ORDER:
                    row = {"Desk": f"<b>{desk}</b>"}
                    for unit in units:
                        match = op_df[(op_df['Unit'] == unit) & (op_df['Desk'] == desk)]
                        row[unit] = "-" if match.empty else agg_staff_html(match)
                    table_data.append(row)
                st.write(pd.DataFrame(table_data).to_html(escape=False, index=False, classes="table table-bordered"), unsafe_allow_html=True)

    else:
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

            if st.session_state.admin_logged_in and st.session_state.dashboard_card_edit:
                st.info("🃏 **Interactive Play Card Edit Mode is ON.** Click `✏️` on any employee card to edit.")
                render_dept_playcard_board(dept_df, key_prefix="dashdept")
            else:
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
                                name = format_staff_name(row['Staff_Name'], row.get('Designation', ''))
                                status_icon = "🔴" if row['Status'] == 'VACANCY' else "🟠" if row['Status'] == 'Transferred' else "🟢"
                                cols[i % 3].markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{status_icon} **{name}**")

                if sic_folders:
                    sic_total = sum([len(active_df[active_df['Department'] == d]) for d in sic_folders])
                    with st.expander(f"👨‍✈️ Shift In-Charge (Total: {sic_total})", expanded=False):
                        for d in sic_folders:
                            st.markdown(f"**{d}**")
                            render_hierarchy(active_df[active_df['Department'] == d])

                if ops_folders:
                    ops_total = sum([len(active_df[active_df['Department'] == d]) for d in ops_folders])
                    with st.expander(f"🏭 Main Plant PCR Staff (Total: {ops_total})", expanded=False):
                        ops_tabs = st.tabs([d.replace("Main Plant Ops - ", "") for d in ops_folders])
                        for tab, dept_name in zip(ops_tabs, ops_folders):
                            with tab:
                                render_hierarchy(active_df[active_df['Department'] == dept_name])

                if chp_folders:
                    chp_total = sum([len(active_df[active_df['Department'] == d]) for d in chp_folders])
                    with st.expander(f"🏭 Coal Handling Plant (Total: {chp_total})", expanded=False):
                        chp_tabs = st.tabs([d.replace("CHP", "").strip() for d in chp_folders])
                        for tab, dept_name in zip(chp_tabs, chp_folders):
                            with tab:
                                render_hierarchy(active_df[active_df['Department'] == dept_name])

                for dept_name in standard_folders:
                    group = active_df[active_df['Department'] == dept_name]
                    if group.empty:
                        continue
                    with st.expander(f"📂 {dept_name} ({len(group)} Staff)", expanded=False):
                        render_hierarchy(group)

# ==============================================================================
# TAB 2: SEARCH & REPORTS
# ==============================================================================
with tab2:
    st.header("Search & Reports")
    search_tabs = st.tabs(["⚡ Shift Operations Search", "🏢 Departmental Staff Search"])

    with search_tabs[0]:
        st.subheader("Search in Shift Operations")
        c_op1, c_op2 = st.columns(2)
        s_unit = c_op1.selectbox("Filter Unit", ["All"] + sorted(ops_df['Unit'].unique().tolist()), key="s_unit")
        s_desk = c_op2.selectbox("Filter Desk", ["All"] + sorted(ops_df['Desk'].unique().tolist()), key="s_desk")
        ops_filtered = ops_df.copy()
        if s_unit != "All":
            ops_filtered = ops_filtered[ops_filtered['Unit'] == s_unit]
        if s_desk != "All":
            ops_filtered = ops_filtered[ops_filtered['Desk'] == s_desk]
        if not ops_filtered.empty:
            c1, c2 = st.columns(2)
            with c1:
                _, _, s_counts = get_global_metrics(ops_filtered, pd.DataFrame(), "Ops")
                if not s_counts.empty:
                    fig_s = px.pie(
                        values=s_counts.values, names=s_counts.index, color=s_counts.index,
                        color_discrete_map={'VACANCY': '#ff4b4b', 'Transferred': '#ffa421', 'Active': '#00CC96'},
                        title="Status", height=250
                    )
                    st.plotly_chart(fig_s, use_container_width=True)
            st.dataframe(ops_filtered[['Unit', 'Desk', 'Staff_Name', 'Designation', 'Status']], use_container_width=True, hide_index=True)
        else:
            st.info("No records found.")

    with search_tabs[1]:
        st.subheader("Search in Departments")
        s_dept = st.selectbox("Filter Department", ["All"] + sorted(dept_df['Department'].unique().tolist()), key="s_dept")
        dept_filtered = dept_df.copy()
        if s_dept != "All":
            dept_filtered = dept_filtered[dept_filtered['Department'] == s_dept]
        if not dept_filtered.empty:
            c1, c2 = st.columns(2)
            with c1:
                _, _, s_counts = get_global_metrics(pd.DataFrame(), dept_filtered, "Dept")
                if not s_counts.empty:
                    fig_s = px.pie(
                        values=s_counts.values, names=s_counts.index, color=s_counts.index,
                        color_discrete_map={'VACANCY': '#ff4b4b', 'Transferred': '#ffa421', 'Active': '#00CC96'},
                        title="Status", height=250
                    )
                    st.plotly_chart(fig_s, use_container_width=True)
            st.dataframe(dept_filtered[['Department', 'Staff_Name', 'Designation', 'Status']], use_container_width=True, hide_index=True)
        else:
            st.info("No records found.")

# ==============================================================================
# TAB 3: ADMIN PLAY CARDS (FLASHCARD EDITOR)
# ==============================================================================
with tab3:
    st.header("🃏 Admin Play Card Editor")
    if not st.session_state.admin_logged_in:
        c_login1, c_login2 = st.columns([2, 1])
        pwd = c_login1.text_input("Enter Admin Password", type="password", key="tab3_pwd")
        if c_login2.button("🔓 Login", type="primary"):
            if pwd == "admin123":
                st.session_state.admin_logged_in = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        top_c1, top_c2, top_c3 = st.columns([2.2, 2.2, 1])
        with top_c1:
            card_filter = st.radio(
                "Filter Play Cards",
                ["All", "🔴 Vacancies Only", "🟠 Transferred Only"],
                horizontal=True
            )
        with top_c2:
            card_search = st.text_input("🔍 Quick Search Name / Designation", placeholder="Type name e.g. Jadhav, AE...")
        with top_c3:
            st.write("")
            if st.button("🔒 Logout"):
                st.session_state.admin_logged_in = False
                st.session_state.active_edit_card = None
                st.rerun()

        st.caption(
            f"Currently editing: **{view_mode}** — Tap **✏️** (or **➕ Fill**) on any Play Card below to edit name, "
            "designation, status, or transfer/swap staff directly."
        )
        st.divider()

        if view_mode == VIEW_OPS:
            render_ops_playcard_board(
                ops_df, dept_df,
                filter_mode=card_filter,
                search_query=card_search.strip(),
                key_prefix="admin"
            )
        else:
            render_dept_playcard_board(
                dept_df,
                filter_mode=card_filter,
                search_query=card_search.strip(),
                key_prefix="admindept"
            )
