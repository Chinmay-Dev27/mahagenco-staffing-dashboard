import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Staffing Dashboard", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        return pd.read_csv(DATA_FILE)
    except FileNotFoundError:
        st.error(f"File {DATA_FILE} not found. Please upload it.")
        return pd.DataFrame(columns=['Unit', 'Desk', 'Status', 'Staff_Details'])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear() # Clear cache to reload new data
    st.success("✅ Database Updated!")

# --- 2. AUTHENTICATION ---
def check_password():
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        
    if not st.session_state['authenticated']:
        st.sidebar.markdown("### 🔐 Admin Login")
        password = st.sidebar.text_input("Enter Password", type="password")
        if password == "admin123": # You can change this password here
            st.session_state['authenticated'] = True
            st.rerun()
        return False
    return True

# --- 3. DASHBOARD MAIN ---
st.title("🏭 Plant Manpower Dashboard")

df = load_data()

# Sidebar Filters
st.sidebar.header("Filter View")
all_units = df['Unit'].unique().tolist() if not df.empty else []
selected_unit = st.sidebar.multiselect("Select Unit", all_units, default=all_units)

if selected_unit:
    df_view = df[df['Unit'].isin(selected_unit)]
else:
    df_view = df

# TABS
tab1, tab2 = st.tabs(["📊 Interactive Heatmap", "📝 Admin Update"])

with tab1:
    if not df_view.empty:
        # PREPARE DATA FOR PLOTLY HEATMAP
        status_map = {'VACANCY': 2, 'Risk (Transfer)': 1, 'OK': 0}
        df_view['Score'] = df_view['Status'].map(status_map).fillna(0)
        
        # Pivot for Score (Color)
        z_data = df_view.pivot_table(index='Desk', columns='Unit', values='Score', aggfunc='max')
        
        # Pivot for Text (Hover info)
        text_data = df_view.pivot_table(index='Desk', columns='Unit', values='Staff_Details', aggfunc=lambda x: ' '.join(str(v) for v in x))
        
        # Fill NaN
        z_data = z_data.fillna(0)
        text_data = text_data.fillna("No Data")
        
        # Reorder Rows (Standard Sequence)
        desired_order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                         'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
        existing_order = [d for d in desired_order if d in z_data.index]
        z_data = z_data.reindex(existing_order)
        text_data = text_data.reindex(existing_order)

        # PLOTLY HEATMAP
        fig = go.Figure(data=go.Heatmap(
            z=z_data.values,
            x=z_data.columns,
            y=z_data.index,
            text=text_data.values,
            hoverinfo='text',
            colorscale=[[0, '#ecfdf5'], [0.5, '#fff7ed'], [1, '#fef2f2']], # Green, Orange, Red
            showscale=False,
            xgap=3, ygap=3
        ))

        # Annotations (Text on cells)
        annotations = []
        for i, row in enumerate(z_data.index):
            for j, col in enumerate(z_data.columns):
                val = z_data.loc[row, col]
                if val == 2:
                    status_text = "VACANCY"
                    color = "#b91c1c"
                elif val == 1:
                    status_text = "RISK"
                    color = "#c2410c"
                else:
                    status_text = "OK"
                    color = "#047857"
                
                annotations.append(dict(
                    x=col, y=row, text=status_text,
                    xref="x", yref="y",
                    showarrow=False, font=dict(color=color, weight='bold', size=14)
                ))
        
        fig.update_layout(
            title="Operational Heatmap (Hover for Staff Details)",
            annotations=annotations,
            height=600,
            margin=dict(l=50, r=50, b=50, t=50)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Hover over any cell to see the specific staff members deployed there.")
    else:
        st.info("No data available for the selected filters.")

with tab2:
    if check_password():
        st.subheader("Update Staffing Record")
        
        if not df.empty:
            col1, col2 = st.columns(2)
            with col1:
                u_input = st.selectbox("Unit", df['Unit'].unique())
                d_input = st.selectbox("Desk", df['Desk'].unique())
            with col2:
                s_input = st.selectbox("Status", ["OK", "VACANCY", "Risk (Transfer)"])
                n_input = st.text_area("Staff Details / Notes")
                
            if st.button("Update Database"):
                mask = (df['Unit'] == u_input) & (df['Desk'] == d_input)
                if mask.any():
                    df.loc[mask, 'Status'] = s_input
                    df.loc[mask, 'Staff_Details'] = n_input
                    save_data(df)
                    st.rerun()
                else:
                    st.warning("Entry not found in master database.")
