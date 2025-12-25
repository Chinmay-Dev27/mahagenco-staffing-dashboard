import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import re
from github import Github
import io
import tempfile

# --- REPORTLAB IMPORTS (The Robust PDF Engine) ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Parli Ops", page_icon="⚡", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'
REPO_NAME = "Chinmay-Dev27/mahagenco-staffing-dashboard"

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #0E1117; border: 1px solid #30333F; border-radius: 10px; padding: 15px; text-align: center; }
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

# --- CHART GENERATION ---
def create_chart_images(df):
    op_df = df[df['Desk'] != 'Shift In-Charge']
    
    # 1. Pie Chart
    status_counts = op_df['Status'].value_counts()
    fig1, ax1 = plt.subplots(figsize=(4, 3))
    colors = {'VACANCY':'#D32F2F', 'Transferred':'#F57C00', 'Active':'#388E3C', 'Long Leave':'#333333'}
    pie_colors = [colors.get(x, '#999999') for x in status_counts.index]
    ax1.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', startangle=90, colors=pie_colors, textprops={'fontsize': 8})
    ax1.set_title('Overall Status', fontsize=10, fontweight='bold')
    
    # 2. Bar Chart
    gaps = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
    if not gaps.empty:
        gap_counts = gaps.groupby(['Unit', 'Status']).size().unstack(fill_value=0)
        fig2, ax2 = plt.subplots(figsize=(5, 3))
        gap_counts.plot(kind='bar', stacked=False, color=[colors.get(x, 'red') for x in gap_counts.columns], ax=ax2)
        ax2.set_title('Critical Gaps by Unit', fontsize=10, fontweight='bold')
        ax2.tick_params(axis='x', rotation=0, labelsize=8)
        ax2.legend(fontsize=7)
        plt.tight_layout()
    else:
        fig2, ax2 = plt.subplots(figsize=(5, 3))
        ax2.text(0.5, 0.5, "No Critical Gaps", ha='center', va='center')
        ax2.axis('off')

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f1, tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f2:
        fig1.savefig(f1.name, format='png', dpi=100)
        fig2.savefig(f2.name, format='png', dpi=100)
        return f1.name, f2.name

# --- REPORTLAB PDF ENGINE (ROBUST LAYOUT) ---
def generate_pdf_report_lab(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=16, spaceAfter=10, textColor=colors.HexColor('#2c3e50'))
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], alignment=TA_CENTER, fontSize=9, textColor=colors.gray)
    
    # 1. Header
    story.append(Paragraph("MAHAGENCO Parli TPS - Operation Shift Report", title_style))
    story.append(Paragraph(f"Official Record Generated on: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}", sub_style))
    story.append(Spacer(1, 20))
    
    # 2. Dashboard Images
    img1_path, img2_path = create_chart_images(df)
    
    # Create a table for side-by-side images
    img1 = Image(img1_path, width=200, height=150)
    img2 = Image(img2_path, width=250, height=150)
    chart_data = [[img1, img2]]
    chart_table = Table(chart_data, colWidths=[230, 280])
    chart_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(chart_table)
    story.append(Spacer(1, 20))

    # 3. Metrics Summary
    op_df = df[df['Desk'] != 'Shift In-Charge']
    active = len(op_df[op_df['Status']=='Active'])
    vacant = len(op_df[op_df['Status']=='VACANCY'])
    transferred = len(op_df[op_df['Status']=='Transferred'])
    
    metric_data = [[f"Total Active: {active}", f"Critical Shortage: {vacant}", f"Transferred (Risk): {transferred}"]]
    metric_table = Table(metric_data, colWidths=[150, 150, 150])
    metric_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F5F7FA')),
        ('BOX', (0,0), (-1,-1), 1, colors.silver),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('TEXTCOLOR', (1,0), (1,0), colors.red), # Shortage Red
        ('TEXTCOLOR', (2,0), (2,0), colors.orange), # Transfer Orange
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 20))

    # 4. Roster Matrix
    story.append(Paragraph("Operational Roster", styles['Heading2']))
    
    units = sorted(df['Unit'].unique())
    desks_order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                   'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
    
    # Table Header
    table_data = [['Position / Desk'] + [str(u) for u in units]]
    
    # Table Styling List (Will append dynamic styles)
    table_styles = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,1), (0,-1), colors.HexColor('#EAEDED')), # Left header gray
        ('FONTNAME', (0,1), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
    ]

    # Style for internal cell text
    cell_style_normal = ParagraphStyle('Cell', fontSize=8, leading=10)
    
    for row_idx, desk in enumerate(desks_order, start=1):
        row_content = [desk]
        for col_idx, u in enumerate(units, start=1):
            matches = op_df[(op_df['Unit'] == u) & (op_df['Desk'] == desk)]
            
            cell_text_parts = []
            has_vacant = False
            has_transfer = False
            
            if matches.empty:
                cell_text_parts.append("-")
            else:
                for _, r in matches.iterrows():
                    nm = format_staff_name(r['Staff_Name'])
                    if r['Status'] == 'VACANCY':
                        # Use Red Bold Text for Vacancy
                        cell_text_parts.append(f"<font color='#D32F2F'><b>VACANT</b></font>")
                        has_vacant = True
                    elif r['Status'] == 'Transferred':
                        # Use Orange Italic Text for Transfer
                        cell_text_parts.append(f"<font color='#E65100'><i>{nm} [TRF]</i></font>")
                        has_transfer = True
                    else:
                        cell_text_parts.append(nm)
            
            # Combine text
            full_text = "<br/>".join(cell_text_parts)
            p = Paragraph(full_text, cell_style_normal)
            row_content.append(p)
            
            # Apply Background Colors Logic
            if has_vacant:
                table_styles.append(('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.HexColor('#FFEBEE'))) # Light Red
            elif has_transfer:
                table_styles.append(('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.HexColor('#FFF3E0'))) # Light Orange
            
        table_data.append(row_content)
    
    # Create Table Flowable
    roster_table = Table(table_data, colWidths=[110, 130, 130, 130])
    roster_table.setStyle(TableStyle(table_styles))
    story.append(roster_table)
    story.append(Spacer(1, 15))
    
    # 5. Shift In Charge Footer
    story.append(Paragraph("Shift In-Charge (EE) On Duty:", styles['Heading4']))
    ee_names = [format_staff_name(x) for x in df[df['Desk']=='Shift In-Charge']['Staff_Name'].unique()]
    story.append(Paragraph(", ".join(ee_names), styles['Normal']))
    
    # 6. Legend
    story.append(Spacer(1, 10))
    legend_text = "<font color='#D32F2F'><b>Red Text/BG</b></font> = Vacancy | <font color='#E65100'><b>Orange Text/BG</b></font> = Transferred"
    story.append(Paragraph(f"Legend: {legend_text}", ParagraphStyle('Leg', fontSize=8, textColor=colors.gray)))

    # Build
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/8/82/Mahagenco_Logo.png/220px-Mahagenco_Logo.png", width=100)
    st.title("Parli TPS Ops")
    
    st.markdown("### 🔍 Global Search")
    search_term = st.text_input("Find Staff Member", placeholder="e.g. Pal, Patil...")
    if search_term and not df.empty:
        res = df[df['Staff_Name'].str.contains(search_term, case=False, na=False)]
        if not res.empty:
            st.success(f"Found {len(res)} matches:")
            for _, r in res.iterrows():
                formatted = format_staff_name(r['Staff_Name'])
                st.markdown(f"<div style='border:1px solid #555; padding:8px; border-radius:5px; margin-bottom:5px;'><b>{formatted}</b><br><small>{r['Unit']} • {r['Desk']}</small></div>", unsafe_allow_html=True)
        else: st.warning("No match found.")

    st.divider()
    if not df.empty:
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📥 Download CSV", data=csv_buffer, file_name="Parli_Staff.csv", mime="text/csv")
        
        if st.button("📄 Generate PDF Report"):
            with st.spinner("Generating Professional Report (ReportLab)..."):
                try:
                    pdf_bytes = generate_pdf_report_lab(df)
                    st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name="MAHAGENCO_Ops_Report.pdf", mime="application/pdf")
                except Exception as e:
                    st.error(f"Error: {e}")

# --- MAIN APP ---
st.title("⚡ Operation Staff Dashboard")
st.markdown(f"**Units:** 6, 7 & 8 | **Last Updated:** {pd.Timestamp.now().strftime('%d-%b-%Y')}")

tab_home, tab_search, tab_admin = st.tabs(["📊 Overview & Roster", "🔍 Search & Reports", "🛠️ Admin Actions"])

# ================= TAB 1 =================
with tab_home:
    if df.empty: st.warning("No data.")
    else:
        op_df = df[df['Desk'] != 'Shift In-Charge']
        c1, c2, c3 = st.columns([1, 1.5, 1.2])
        
        with c1:
            st.markdown("##### 📊 Status")
            fig1 = px.pie(op_df['Status'].value_counts().reset_index(), values='count', names='Status', 
                          color='Status', color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4)
            fig1.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=0,b=0), height=200)
            st.plotly_chart(fig1, use_container_width=True)

        with c2:
            st.markdown("##### ⚠️ Gaps by Unit")
            gaps_df = op_df[op_df['Status'].isin(['VACANCY', 'Transferred'])]
            if not gaps_df.empty:
                fig2 = px.histogram(gaps_df, x="Unit", color="Status", barmode="group",
                                    color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421'}, text_auto=True)
                fig2.update_layout(xaxis_title=None, yaxis_title=None, showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=10,b=10), height=200)
                st.plotly_chart(fig2, use_container_width=True)
            else: st.success("No Manpower Gaps!")

        with c3:
            st.markdown("##### Key Metrics")
            m1, m2 = st.columns(2)
            m1.metric("🚨 Shortage", len(op_df[op_df['Status'] == 'VACANCY']), delta_color="inverse")
            m2.metric("🟠 Transferred", len(op_df[op_df['Status'] == 'Transferred']), delta_color="inverse")
            st.metric("✅ Total Active", len(op_df[op_df['Status'] == 'Active']))

        st.divider()
        st.markdown("### 👨‍✈️ Shift In-Charge (EE)")
        ee_rows = df[df['Desk'] == 'Shift In-Charge']['Staff_Name'].unique()
        cols = st.columns(len(ee_rows) if len(ee_rows)>0 else 1)
        for i, name in enumerate(ee_rows):
            clean_name = re.sub(r'\s*EE\b', '', name, flags=re.IGNORECASE).strip()
            cols[i].info(f"**{clean_name}**")

        st.divider()
        col_head, col_tog = st.columns([3, 1])
        with col_head: st.subheader("🏭 Unit Status Map")
        with col_tog: mobile_view = st.toggle("📱 Mobile Cards", value=False)

        if mobile_view:
            units = sorted(op_df['Unit'].unique())
            tabs = st.tabs(units)
            for i, unit in enumerate(units):
                with tabs[i]:
                    unit_data = op_df[op_df['Unit'] == unit]
                    for _, row in unit_data.iterrows():
                        name = format_staff_name(row['Staff_Name'])
                        color = "#00CC96" if row['Status']=="Active" else "#ff4b4b" if row['Status']=="VACANCY" else "#ffa421"
                        st.markdown(f"""<div class="card-container" style="border-left: 5px solid {color};"><div style="font-weight:bold; font-size:1.1em; color:white;">{row['Desk']}</div><div style="margin-top:5px; color:{color}; font-weight:500;">{name}</div><div style="font-size:0.8em; color:#aaa;">Status: {row['Status']}</div></div>""", unsafe_allow_html=True)
        else:
            def agg_staff_html(x):
                html = []
                for _, row in x.iterrows():
                    name = format_staff_name(row['Staff_Name'])
                    if row['Status'] == 'VACANCY': html.append(f'<div class="badge-vacant">🔴 VACANT</div>')
                    elif row['Status'] == 'Transferred': html.append(f'<div class="badge-transfer">🟠 {name}</div>')
                    else: html.append(f'<div class="badge-active">👤 {name}</div>')
                return "".join(html)

            desks = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            units = sorted(op_df['Unit'].unique())
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
        with c1:
            st.subheader("🚨 Shortages")
            st.dataframe(op_df[op_df['Status']=='VACANCY'][['Unit','Desk','Action_Required']], use_container_width=True, hide_index=True)
        with c2:
            st.subheader("🟠 Transfers")
            trf = op_df[op_df['Status']=='Transferred'][['Unit','Desk','Staff_Name']].copy()
            if not trf.empty: trf['Staff_Name'] = trf['Staff_Name'].apply(format_staff_name)
            st.dataframe(trf, use_container_width=True, hide_index=True)

# ================= TAB 2 =================
with tab_search:
    st.header("🔍 Unit & Desk Analysis")
    if not df.empty:
        c1, c2 = st.columns(2)
        u_sel = c1.selectbox("Select Unit", sorted(df['Unit'].unique().astype(str)))
        d_sel = c2.selectbox("Select Desk", sorted(df[df['Unit']==u_sel]['Desk'].unique().astype(str)))
        st.markdown("---")
        subset = df[(df['Unit']==u_sel) & (df['Desk']==d_sel)]
        if subset.empty: st.info("No records.")
        else:
            c_ch, c_li = st.columns([1, 2])
            with c_ch:
                fig = px.pie(subset['Status'].value_counts().reset_index(), values='count', names='Status', color='Status',
                             color_discrete_map={'VACANCY':'#ff4b4b', 'Transferred':'#ffa421', 'Active':'#00CC96'}, hole=0.4)
                fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(t=0,b=0), height=200)
                st.plotly_chart(fig, use_container_width=True)
            with c_li:
                st.markdown(f"#### Roster: {u_sel} - {d_sel}")
                for _, row in subset.iterrows():
                    name = format_staff_name(row['Staff_Name'])
                    if row['Status']=='VACANCY': st.error(f"🔴 **VACANT** ({row['Action_Required']})")
                    elif row['Status']=='Transferred': st.warning(f"🟠 **{name}** - Transferred")
                    else: st.success(f"👤 **{name}** - Active")

# ================= TAB 3 =================
with tab_admin:
    st.header("🛠️ Admin Tools")
    if not st.session_state.admin_logged_in:
        if st.text_input("Password", type="password") == "admin123" and st.button("Login"):
            st.session_state.admin_logged_in = True
            st.rerun()
    else:
        if st.button("🚪 Logout"):
            st.session_state.admin_logged_in = False
            st.rerun()
        st.divider()
        act = st.radio("Action:", ["🔄 Transfer", "✏️ Change Status", "📝 Update Details", "➕ Add Staff"], horizontal=True)
        st.markdown("---")
        
        if act == "📝 Update Details":
            c1, c2 = st.columns(2)
            u = c1.selectbox("Unit", df['Unit'].unique())
            d = c2.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
            rows = df[(df['Unit']==u) & (df['Desk']==d) & (df['Status']!='VACANCY')]
            if not rows.empty:
                p = st.selectbox("Staff", rows['Staff_Name'].unique())
                idx = df[(df['Unit']==u) & (df['Desk']==d) & (df['Staff_Name']==p)].index[0]
                n_name = c1.text_input("Name", value=df.at[idx,'Staff_Name'])
                n_desg = c2.selectbox("Designation", ["-- Select --", "JE", "AE", "Dy.EE", "Add.EE", "EE"])
                if st.button("Update"):
                    final = f"{n_name} ({n_desg})" if n_desg != "-- Select --" else n_name
                    df.at[idx, 'Staff_Name'] = final
                    save_local(df); update_github(df); st.success("Updated!"); st.rerun()

        elif act == "✏️ Change Status":
            c1, c2 = st.columns(2)
            u = c1.selectbox("Unit", df['Unit'].unique())
            d = c2.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
            rows = df[(df['Unit']==u) & (df['Desk']==d)]
            if not rows.empty:
                p = st.selectbox("Staff", rows['Staff_Name'].unique())
                idx = df[(df['Unit']==u) & (df['Desk']==d) & (df['Staff_Name']==p)].index[0]
                stat = st.selectbox("New Status", ["Active", "Transferred", "VACANCY", "Long Leave"])
                if st.button("Update"):
                    df.at[idx, 'Status'] = stat
                    if stat == "VACANCY":
                        df.at[idx, 'Staff_Name'] = "VACANT POSITION"
                        df.at[idx, 'Action_Required'] = "Manpower Shortage"
                    save_local(df); update_github(df); st.success("Status Updated!"); st.rerun()

        elif act == "🔄 Transfer":
            c1, c2 = st.columns(2)
            u1 = c1.selectbox("From Unit", df['Unit'].unique())
            d1 = c1.selectbox("From Desk", df[df['Unit']==u1]['Desk'].unique())
            ppl = df[(df['Unit']==u1) & (df['Desk']==d1) & (df['Staff_Name']!='VACANT POSITION')]['Staff_Name'].unique()
            p = c1.selectbox("Person", ppl) if len(ppl)>0 else None
            u2 = c2.selectbox("To Unit", df['Unit'].unique())
            d2 = c2.selectbox("To Desk", df[df['Unit']==u2]['Desk'].unique())
            old_act = st.radio("Old Seat:", ["Mark VACANT", "No Change"], horizontal=True)
            if p and st.button("Transfer"):
                src = df[(df['Unit']==u1) & (df['Desk']==d1) & (df['Staff_Name']==p)].index[0]
                tgt_vac = df[(df['Unit']==u2) & (df['Desk']==d2) & (df['Status']=='VACANCY')]
                if not tgt_vac.empty:
                    df.at[tgt_vac.index[0], 'Staff_Name'] = p; df.at[tgt_vac.index[0], 'Status'] = "Active"
                else:
                    df = pd.concat([df, pd.DataFrame([{"Unit":u2, "Desk":d2, "Staff_Name":p, "Status":"Active"}])], ignore_index=True)
                if old_act == "Mark VACANT":
                    df.at[src, 'Staff_Name'] = "VACANT POSITION"; df.at[src, 'Status'] = "VACANCY"; df.at[src, 'Action_Required'] = "Manpower Shortage"
                save_local(df); update_github(df); st.success("Transferred!"); st.rerun()

        elif act == "➕ Add Staff":
            u = st.selectbox("Unit", df['Unit'].unique())
            d = st.selectbox("Desk", df[df['Unit']==u]['Desk'].unique())
            n = st.text_input("Name")
            if st.button("Add"):
                vac = df[(df['Unit']==u) & (df['Desk']==d) & (df['Status']=='VACANCY')]
                if not vac.empty:
                    df.at[vac.index[0], 'Staff_Name'] = n; df.at[vac.index[0], 'Status'] = "Active"
                else:
                    df = pd.concat([df, pd.DataFrame([{"Unit":u, "Desk":d, "Staff_Name":n, "Status":"Active"}])], ignore_index=True)
                save_local(df); update_github(df); st.success("Added!"); st.rerun()
