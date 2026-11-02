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
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak, KeepInFrame
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

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

# Full name auto-mapper if CSV still has old initials for Shift In-Charge
SIC_NAME_MAP = {
    "R. V. Bhale": "Renukadas Bhale",
    "J. S. Dumne": "Jayant Dumne",
    "S. B. Pawar": "Sunil Pawar",
    "S. P. Kale": "Sunil Kale",
    "K. G. Rathod": "Kundan Rathod",
    "S. B. Gaikwad": "Sumeet Gaikwad",
    "P. S. Yallawar": "Prashant Yallawar",
    "J. N. Deshmane": "Jagannath Deshmane",
    "M. N. Munde": "Mahadev Munde",
    "S. N. Oholkar": "Sunit Oholkar"
}

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #0E1117; border: 1px solid #30333F; border-radius: 10px; padding: 15px; text-align: center; }
    .badge-vacant { background-color: #ff4b4b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 3px;}
    .badge-transfer { background-color: #ffa421; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; margin-bottom: 3px;}
    .badge-active { background-color: #e6fffa; color: #047857; border: 1px solid #047857; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 0.85em; display: inline-block; margin-bottom: 3px;}
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
        df = df.fillna("")
        # Normalize any row where Staff_Name is VACANT so Status is always VACANCY
        vac_mask = df['Staff_Name'].astype(str).str.strip().str.upper() == 'VACANT'
        df.loc[vac_mask, 'Status'] = 'VACANCY'
        # Auto-expand Shift In-Charge initials if present
        if filename == DEPT_FILE and 'Department' in df.columns:
            sic_mask = df['Department'].astype(str).str.contains('Shift In-Charge', na=False)
            df.loc[sic_mask, 'Staff_Name'] = df.loc[sic_mask, 'Staff_Name'].apply(
                lambda x: SIC_NAME_MAP.get(str(x).strip(), str(x).strip())
            )
        return df
    except Exception:
        return pd.DataFrame()

def save_and_sync(df, filename):
    vac_mask = df['Staff_Name'].astype(str).str.strip().str.upper() == 'VACANT'
    df.loc[vac_mask, 'Status'] = 'VACANCY'
    df.to_csv(filename, index=False)
    st.cache_data.clear()
    update_github(df, filename)

def format_staff_name(raw_name, desg=""):
    if "VACANT" in str(raw_name).upper():
        return "VACANT"
    clean = re.sub(r'\s*\((Transferred|Trf|transferred)\)', '', str(raw_name), flags=re.IGNORECASE).strip()
    clean = SIC_NAME_MAP.get(clean, clean)
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

# --- UNIVERSAL METRICS HELPER ---
def calculate_metrics(df):
    if df.empty:
        return 0, 0, pd.Series()
    is_vac = (df['Status'] == 'VACANCY') | (df['Staff_Name'].astype(str).str.contains("VACANT", case=False, na=False))
    staff_only = df[~is_vac].copy()
    staff_only['Staff_Name'] = staff_only['Staff_Name'].astype(str).str.strip()
    staff_only['Status_Rank'] = staff_only['Status'].apply(lambda x: 2 if 'Transferred' in str(x) else 1)
    staff_only = staff_only.sort_values(by=['Staff_Name', 'Status_Rank'], ascending=[True, False])
    unique_staff = staff_only.drop_duplicates(subset=['Staff_Name'], keep='first')
    transferred = len(unique_staff[unique_staff['Status'] == 'Transferred'])
    vacant = int(is_vac.sum())
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


# ==============================================================================
# ALIGNED, SINGLE-PAGE PDF ENGINE
# ==============================================================================
def format_pdf_staff_line(r):
    """Formats a single staff row cleanly for PDF Paragraph without nested sub-tables."""
    status = str(r.get('Status', 'Active'))
    raw_name = str(r.get('Staff_Name', '')).strip()
    desg = str(r.get('Designation', '')).strip()
    is_vac = (status == 'VACANCY') or ('VACANT' in raw_name.upper())

    if is_vac:
        return '<font color="#dc2626"><b>[X] VACANT</b></font>'
    nm = format_staff_name(raw_name, desg)
    if status == 'Transferred':
        return f'<font color="#d97706"><b>[Trf]</b> <i>{nm}</i></font>'
    return f'<font color="#0f172a">{nm}</font>'


def generate_combined_pdf(ops_df, dept_df, report_type="Summary"):
    buffer = io.BytesIO()
    # Landscape A4 = 841.89 x 595.27 pt. With 25pt margins, usable width = 791pt, height = 545pt
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=25, leftMargin=25, topMargin=18, bottomMargin=18
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'PDFTitle', parent=styles['Title'],
        fontName='Helvetica-Bold', fontSize=14, leading=16, alignment=TA_CENTER, spaceAfter=2
    )
    sub_style = ParagraphStyle(
        'PDFSub', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#475569'), spaceAfter=8
    )
    sec_heading = ParagraphStyle(
        'PDFSec', parent=styles['Heading3'],
        fontName='Helvetica-Bold', fontSize=10, leading=12, textColor=colors.HexColor('#1e293b'), spaceBefore=4, spaceAfter=4
    )
    cell_style = ParagraphStyle(
        'PDFCell', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=10.5, alignment=TA_LEFT
    )
    desk_col_style = ParagraphStyle(
        'PDFDeskCol', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.HexColor('#1e293b')
    )
    hdr_style = ParagraphStyle(
        'PDFHdr', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=colors.white
    )

    story = []

    # ------------------------------------------------------------------
    # 1. SINGLE PAGE OP VACANCY OVERVIEW (STRICTLY FITS ON 1 PAGE)
    # ------------------------------------------------------------------
    if report_type == "Single Page Op Vacancy":
        page_flowables = []
        page_flowables.append(Paragraph("MAHAGENCO Parli TPS — Operation Staffing & Vacancy Overview", title_style))
        page_flowables.append(Paragraph(f"Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", sub_style))

        # --- Section A: Complete Shift In-Charge (EE) Roster (Unit 6&7 and Unit 8) ---
        sic_df = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)] if not dept_df.empty else pd.DataFrame()
        if not sic_df.empty:
            page_flowables.append(Paragraph("1. Shift In-Charge (EE) Roster", sec_heading))
            u67_rows = sic_df[sic_df['Department'] == 'Shift In-Charge (U6&7)']
            u8_rows = sic_df[sic_df['Department'] == 'Shift In-Charge (U8)']

            u67_lines = "<br/>".join([format_pdf_staff_line(r) for _, r in u67_rows.iterrows()]) or "-"
            u8_lines = "<br/>".join([format_pdf_staff_line(r) for _, r in u8_rows.iterrows()]) or "-"

            sic_table_data = [
                [
                    Paragraph("<b>Position</b>", hdr_style),
                    Paragraph("<b>Unit 6 & 7 (Common Pool)</b>", hdr_style),
                    Paragraph("<b>Unit 8</b>", hdr_style)
                ],
                [
                    Paragraph("Shift In-Charge (EE)", desk_col_style),
                    Paragraph(u67_lines, cell_style),
                    Paragraph(u8_lines, cell_style)
                ]
            ]
            t_sic = Table(sic_table_data, colWidths=[125, 333, 333])
            t_sic.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f1f5f9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            page_flowables.append(t_sic)
            page_flowables.append(Spacer(1, 6))

        # --- Section B: Main Plant PCR Shift Operations Roster (Full Width 791pt) ---
        if not ops_df.empty:
            page_flowables.append(Paragraph("2. Main Plant Shift Operations Roster", sec_heading))
            units = sorted(ops_df['Unit'].unique())
            header_row = [Paragraph("<b>Position / Desk</b>", hdr_style)] + [Paragraph(f"<b>{u}</b>", hdr_style) for u in units]
            main_data = [header_row]

            for desk in DESK_ORDER:
                row = [Paragraph(desk, desk_col_style)]
                for u in units:
                    matches = ops_df[(ops_df['Unit'] == u) & (ops_df['Desk'] == desk)]
                    if matches.empty:
                        row.append(Paragraph("-", cell_style))
                    else:
                        lines_html = "<br/>".join([format_pdf_staff_line(r) for _, r in matches.iterrows()])
                        row.append(Paragraph(lines_html, cell_style))
                main_data.append(row)

            # Total width = 125 + 222 + 222 + 222 = 791pt
            t_main = Table(main_data, colWidths=[125, 222, 222, 222])
            t_main.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f8fafc')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 3.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            page_flowables.append(t_main)
            page_flowables.append(Spacer(1, 6))

        # --- Section C: Summary of Vacancies & Pending Transfers ---
        page_flowables.append(Paragraph("3. Action Required — Open Vacancies & Pending Transfers", sec_heading))
        issue_rows = [
            [
                Paragraph("<b>Unit / Pool</b>", hdr_style),
                Paragraph("<b>Desk / Position</b>", hdr_style),
                Paragraph("<b>Staff / Slot</b>", hdr_style),
                Paragraph("<b>Status</b>", hdr_style)
            ]
        ]

        # Include Shift In-Charge anomalies
        if not sic_df.empty:
            sic_issues = sic_df[
                (sic_df['Status'].isin(['VACANCY', 'Transferred'])) |
                (sic_df['Staff_Name'].astype(str).str.upper().str.contains('VACANT'))
            ]
            for _, r in sic_issues.iterrows():
                u_lbl = "Unit 6 & 7" if "U6&7" in str(r['Department']) else "Unit 8"
                is_v = (r['Status'] == 'VACANCY') or ('VACANT' in str(r['Staff_Name']).upper())
                nm_str = "VACANT" if is_v else format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                st_html = '<font color="#dc2626"><b>VACANCY</b></font>' if is_v else '<font color="#d97706"><b>Transferred</b></font>'
                issue_rows.append([
                    Paragraph(u_lbl, cell_style),
                    Paragraph("Shift In-Charge (EE)", cell_style),
                    Paragraph(nm_str, cell_style),
                    Paragraph(st_html, cell_style)
                ])

        # Include Main Plant Ops anomalies
        if not ops_df.empty:
            op_issues = ops_df[
                (ops_df['Status'].isin(['VACANCY', 'Transferred'])) |
                (ops_df['Staff_Name'].astype(str).str.upper().str.contains('VACANT'))
            ].sort_values(['Unit', 'Desk'])
            for _, r in op_issues.iterrows():
                is_v = (r['Status'] == 'VACANCY') or ('VACANT' in str(r['Staff_Name']).upper())
                nm_str = "VACANT" if is_v else format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                st_html = '<font color="#dc2626"><b>VACANCY</b></font>' if is_v else '<font color="#d97706"><b>Transferred</b></font>'
                issue_rows.append([
                    Paragraph(str(r['Unit']), cell_style),
                    Paragraph(str(r['Desk']), cell_style),
                    Paragraph(nm_str, cell_style),
                    Paragraph(st_html, cell_style)
                ])

        if len(issue_rows) > 1:
            t_list = Table(issue_rows, colWidths=[125, 222, 294, 150])
            t_list.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            page_flowables.append(t_list)
        else:
            page_flowables.append(Paragraph("No vacancies or pending transfers found in Shift Operations.", cell_style))

        # KeepInFrame guarantees the entire report shrinks smoothly to fit on 1 single Landscape A4 page
        story.append(KeepInFrame(791, 555, page_flowables, mode='shrink'))

    # ------------------------------------------------------------------
    # 2. CONSOLIDATED SUMMARY / DETAILED REPORTS
    # ------------------------------------------------------------------
    else:
        story.append(Paragraph("MAHAGENCO Parli TPS — Consolidated Staffing Report", title_style))
        story.append(Paragraph(f"Type: {report_type} | Generated: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", sub_style))
        story.append(Spacer(1, 10))

        v_total, t_total, _ = get_global_metrics(ops_df, dept_df, "Global")
        v_ops, t_ops, _ = get_global_metrics(ops_df, dept_df, "Ops")
        v_dept, t_dept, _ = get_global_metrics(pd.DataFrame(), dept_df, "Dept")

        summary_data = [
            ['Section', 'Total Vacancies', 'Total Transferred'],
            ['Shift Operations (Inc. In-Charge)', v_ops, t_ops],
            ['Departmental Staff', v_dept, t_dept],
            ['TOTAL PLANT', v_total, t_total]
        ]
        t_sum = Table(summary_data, colWidths=[350, 220, 220])
        t_sum.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#94a3b8')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER')
        ]))
        story.append(t_sum)
        story.append(Spacer(1, 15))

        story.append(Paragraph("1. Shift Operations (Main Plant)", sec_heading))

        sic_df = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)] if not dept_df.empty else pd.DataFrame()
        if not sic_df.empty:
            u67_lines = ", ".join([
                "VACANT" if (r['Status'] == 'VACANCY' or 'VACANT' in str(r['Staff_Name']).upper())
                else format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                for _, r in sic_df[sic_df['Department'] == 'Shift In-Charge (U6&7)'].iterrows()
            ])
            u8_lines = ", ".join([
                "VACANT" if (r['Status'] == 'VACANCY' or 'VACANT' in str(r['Staff_Name']).upper())
                else format_staff_name(r['Staff_Name'], r.get('Designation', ''))
                for _, r in sic_df[sic_df['Department'] == 'Shift In-Charge (U8)'].iterrows()
            ])
            sic_data = [
                [Paragraph("<b>Shift In-Charge Pool</b>", hdr_style), Paragraph("<b>Assigned Officers (EE)</b>", hdr_style)],
                [Paragraph("Unit 6 & 7 (Common)", desk_col_style), Paragraph(u67_lines, cell_style)],
                [Paragraph("Unit 8", desk_col_style), Paragraph(u8_lines, cell_style)]
            ]
            t_sic = Table(sic_data, colWidths=[180, 611])
            t_sic.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f1f5f9'))
            ]))
            story.append(t_sic)
            story.append(Spacer(1, 10))

        if report_type == "Summary (Numbers)":
            agg_data = [['Unit', 'Active Staff', 'Vacant', 'Transferred']]
            if not ops_df.empty:
                for name, group in ops_df.groupby('Unit'):
                    v, t, s = calculate_metrics(group)
                    agg_data.append([name, s.get('Active', 0), v, t])
            t_agg = Table(agg_data, colWidths=[250, 180, 180, 181])
            t_agg.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
            ]))
            story.append(t_agg)
        else:
            if not ops_df.empty:
                units = sorted(ops_df['Unit'].unique())
                header_row = [Paragraph("<b>Position / Desk</b>", hdr_style)] + [Paragraph(f"<b>{u}</b>", hdr_style) for u in units]
                main_data = [header_row]
                for desk in DESK_ORDER:
                    row = [Paragraph(desk, desk_col_style)]
                    for u in units:
                        matches = ops_df[(ops_df['Unit'] == u) & (ops_df['Desk'] == desk)]
                        if matches.empty:
                            row.append(Paragraph("-", cell_style))
                        else:
                            lines_html = "<br/>".join([format_pdf_staff_line(r) for _, r in matches.iterrows()])
                            row.append(Paragraph(lines_html, cell_style))
                    main_data.append(row)
                t_main = Table(main_data, colWidths=[125, 222, 222, 222])
                t_main.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(t_main)

        story.append(PageBreak())
        story.append(Paragraph("2. Departmental Staff", sec_heading))

        if not dept_df.empty:
            if report_type == "Summary (Numbers)":
                agg_data = [['Department', 'Active Staff', 'Vacant', 'Transferred']]
                for name, group in dept_df.groupby('Department'):
                    v, t, s = calculate_metrics(group)
                    agg_data.append([name, s.get('Active', 0), v, t])
                t_agg = Table(agg_data, colWidths=[350, 147, 147, 147], repeatRows=1)
                t_agg.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                story.append(t_agg)
            else:
                for d in sorted(dept_df['Department'].unique()):
                    group = dept_df[dept_df['Department'] == d]
                    if group.empty:
                        continue
                    story.append(Paragraph(f"{d} ({len(group)})", sec_heading))
                    d_data = [['Name', 'Designation', 'Status']]
                    group = group.copy()
                    group['Rank'] = group['Designation'].apply(get_rank_level)
                    group = group.sort_values('Rank')
                    for _, r in group.iterrows():
                        d_data.append([format_staff_name(r['Staff_Name']), str(r['Designation']), r['Status']])
                    t_dept = Table(d_data, colWidths=[350, 241, 200], repeatRows=1)
                    t_dept.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                    ]))
                    story.append(t_dept)
                    story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ==============================================================================
# INTERACTIVE PLAY CARD (FLASHCARD) ENGINE
# ==============================================================================
def render_playcard(df, idx, is_ops, target_file, key_prefix="card"):
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
                    if new_status == "VACANCY" or not new_name.strip() or new_name.strip().upper() == "VACANT":
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
                final_status = "Active" if (a_name.strip() and a_name.strip().upper() != "VACANT") else "VACANCY"

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

            if st.session_state.admin_logged_in and st.session_state.dashboard_card_edit:
                st.info("🃏 **Interactive Play Card Edit Mode is ON.** Click `✏️` on any card below to edit names, status, or transfer staff.")
                render_ops_playcard_board(ops_df, dept_df, key_prefix="dash")
            else:
                def agg_staff_html(x):
                    html = []
                    for _, row in x.iterrows():
                        is_v = (row['Status'] == 'VACANCY') or ('VACANT' in str(row['Staff_Name']).upper())
                        name = format_staff_name(row['Staff_Name'], row.get('Designation', ''))
                        if is_v:
                            html.append('<div class="badge-vacant">🔴 VACANT</div>')
                        elif row['Status'] == 'Transferred':
                            html.append(f'<div class="badge-transfer">🟠 {name}</div>')
                        else:
                            html.append(f'<div class="badge-active">👤 {name}</div>')
                    return "<br/>".join(html)

                st.subheader("👨‍✈️ Shift In-Charge (EE)")
                sic_dept = dept_df[dept_df['Department'].str.contains('Shift In-Charge', na=False)]
                if not sic_dept.empty:
                    u67_df = sic_dept[sic_dept['Department'] == 'Shift In-Charge (U6&7)']
                    u8_df = sic_dept[sic_dept['Department'] == 'Shift In-Charge (U8)']
                    sic_html_table = [{
                        "Unit 6 & 7 (Common Pool)": agg_staff_html(u67_df) if not u67_df.empty else "-",
                        "Unit 8": agg_staff_html(u8_df) if not u8_df.empty else "-"
                    }]
                    st.write(pd.DataFrame(sic_html_table).to_html(escape=False, index=False, classes="table table-bordered"), unsafe_allow_html=True)

                st.divider()

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
                                is_v = (row['Status'] == 'VACANCY') or ('VACANT' in str(row['Staff_Name']).upper())
                                name = "VACANT" if is_v else format_staff_name(row['Staff_Name'], row.get('Designation', ''))
                                status_icon = "🔴" if is_v else ("🟠" if row['Status'] == 'Transferred' else "🟢")
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
