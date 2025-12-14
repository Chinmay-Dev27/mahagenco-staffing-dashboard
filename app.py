import streamlit as st
import pandas as pd
import altair as alt

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Staffing", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_FILE)
        # Ensure 'Staff_Details' is string to avoid errors
        df['Staff_Details'] = df['Staff_Details'].fillna("No Data").astype(str)
        return df
    except FileNotFoundError:
        st.error(f"File {DATA_FILE} not found.")
        return pd.DataFrame()

def save_data(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

# --- 2. AUTHENTICATION ---
def check_password():
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    
    if not st.session_state['authenticated']:
        pwd = st.sidebar.text_input("🔐 Admin Password", type="password")
        if pwd == "admin123":
            st.session_state['authenticated'] = True
            st.rerun()
        return False
    return True

# --- 3. POPUP DIALOG FUNCTION ---
@st.dialog("Staffing Details")
def show_details(unit, desk, status, details):
    st.markdown(f"### {unit} - {desk}")
    
    # Color code the status
    if status == "VACANCY":
        st.error(f"🚨 STATUS: {status}")
    elif "Risk" in status:
        st.warning(f"⚠️ STATUS: {status}")
    else:
        st.success(f"✅ STATUS: {status}")
        
    st.markdown("---")
    st.markdown("#### 👥 Staff Deployed:")
    # Format details nicely (replace commas with new lines for readability)
    formatted_details = details.replace(",", "\n- ").replace("|", "\n\n**Note:**")
    st.markdown(f"- {formatted_details}")
    st.markdown("---")

# --- 4. MAIN APP ---
st.title("🏭 Interactive Manpower Dashboard")

df = load_data()

# --- INTERACTIVE HEATMAP (Altair) ---
st.subheader("👆 Click on any block to view details")

# Define Colors
domain = ['VACANCY', 'Risk (Transfer)', 'OK']
range_ = ['#ef4444', '#f97316', '#10b981'] # Red, Orange, Green

# Create the Chart
base = alt.Chart(df).encode(
    x=alt.X('Unit', axis=alt.Axis(title=None, labelFontSize=14, labelFontWeight='bold')),
    y=alt.Y('Desk', sort=['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                          'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)'],
            axis=alt.Axis(title=None, labelFontSize=12)),
)

heatmap = base.mark_rect().encode(
    color=alt.Color('Status', scale=alt.Scale(domain=domain, range=range_), legend=None),
    tooltip=['Unit', 'Desk', 'Status']
).properties(height=500)

text = base.mark_text(baseline='middle').encode(
    text='Status',
    color=alt.value('white') # White text on colored background
)

# Combine heatmap + text
chart = (heatmap + text).interactive()

# Render Chart with Selection Event
event = st.altair_chart(chart, use_container_width=True, on_select="rerun", theme="streamlit")

# --- HANDLE CLICK EVENT ---
if len(event.selection.point_indices) > 0:
    # Get the clicked row index
    selected_index = event.selection.point_indices[0]
    selected_row = df.iloc[selected_index]
    
    # Trigger the Popup Dialog
    show_details(
        selected_row['Unit'], 
        selected_row['Desk'], 
        selected_row['Status'], 
        selected_row['Staff_Details']
    )

st.caption("ℹ️ Note: If the popup doesn't appear, ensure you are clicking directly on a colored block.")

# --- ADMIN SECTION ---
st.markdown("---")
with st.expander("🛠️ Admin Tools (Update Data)"):
    if check_password():
        st.write("Edit the database below:")
        
        # Grid layout for editing
        col1, col2 = st.columns(2)
        with col1:
            u_input = st.selectbox("Select Unit", df['Unit'].unique())
            d_input = st.selectbox("Select Desk", df['Desk'].unique())
        with col2:
            s_input = st.selectbox("New Status", ["OK", "VACANCY", "Risk (Transfer)"])
            n_input = st.text_area("Update Staff Names")
            
        if st.button("Update Record"):
            mask = (df['Unit'] == u_input) & (df['Desk'] == d_input)
            df.loc[mask, 'Status'] = s_input
            df.loc[mask, 'Staff_Details'] = n_input
            save_data(df)
            st.success("Updated! Refreshing...")
            st.rerun()
