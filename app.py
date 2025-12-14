import streamlit as st
import pandas as pd
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="Mahagenco Smart Dashboard", layout="wide")
DATA_FILE = 'stitched_staffing_data.csv'

# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(DATA_FILE)
        df['Status'] = df['Status'].astype(str)
        df['Staff_Name'] = df['Staff_Name'].astype(str)
        return df
    except FileNotFoundError:
        return pd.DataFrame()

def save_data(df):
    df.to_csv(DATA_FILE, index=False)
    st.cache_data.clear()

df = load_data()

# --- 2. SIDEBAR ---
st.sidebar.title("🏭 Mahagenco")
page = st.sidebar.radio("Go to:", ["Dashboard Home", "Search & Graphs", "Admin (Smart Editor)"])

# --- PAGE 1: DASHBOARD HOME ---
if page == "Dashboard Home":
    st.title("🏭 Plant Status Overview")
    
    if df.empty:
        st.error("No data found. Please check your CSV file.")
    else:
        # METRICS
        c1, c2, c3 = st.columns(3)
        vac_count = len(df[df['Status'] == 'VACANCY'])
        risk_count = len(df[df['Status'] == 'Transferred'])
        c1.metric("🚨 Vacancies", vac_count)
        c2.metric("⚠️ Transfers", risk_count)
        c3.metric("✅ Active Staff", len(df[df['Status'] == 'Active']))
        
        st.markdown("---")
        
        # HEATMAP
        st.subheader("1. Operational Heatmap")
        
        def get_aggregated_status(sub_df):
            statuses = sub_df['Status'].values
            if 'VACANCY' in statuses: return 'VACANCY'
            if 'Transferred' in statuses: return 'Risk (Transfer)'
            return 'OK'
            
        if not df.empty:
            heatmap_data = df.groupby(['Unit', 'Desk']).apply(get_aggregated_status).unstack()
            heatmap_data = heatmap_data.fillna("OK")
            
            # Sort Desks
            order = ['PCR In-Charge', 'Turbine Control Desk', 'Boiler Control Desk', 
                     'Drum Level Desk', 'Boiler API (BAPI)', 'Turbine API (TAPI)']
            # Handle sorting safely
            existing_order = [d for d in order if d in heatmap_data.index]
            remaining = [d for d in heatmap_data.index if d not in order]
            heatmap_data = heatmap_data.reindex(existing_order + remaining)
            
            def color_map(val):
                val = str(val)
                if val == 'VACANCY': return 'background-color: #ef4444; color: white; font-weight: bold; text-align: center'
                if 'Risk' in val: return 'background-color: #f97316; color: white; font-weight: bold; text-align: center'
                return 'background-color: #10b981; color: white; text-align: center'
                
            st.dataframe(heatmap_data.style.map(color_map), use_container_width=True)

        # ALERTS
        st.markdown("---")
        st.subheader("🔔 Action Items")
        alerts = df[df['Status'].isin(['VACANCY', 'Transferred'])].copy()
        if not alerts.empty:
            def highlight(row):
                if row['Status'] == 'VACANCY': return ['background-color: #fee2e2; color: #991b1b'] * len(row)
                return ['background-color: #ffedd5; color: #9a3412'] * len(row)

            st.dataframe(
                alerts[['Unit', 'Desk', 'Staff_Name', 'Status', 'Action_Required']].style.apply(highlight, axis=1),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.success("All positions fulfilled.")

# --- PAGE 2: SEARCH & GRAPHS ---
elif page == "Search & Graphs":
    st.title("📊 Detailed Analysis")
    
    if df.empty:
        st.warning("No Data")
    else:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            u_sort = sorted(df['Unit'].unique().astype(str))
            sel_unit = st.selectbox("Unit", u_sort)
        with c2:
            d_sort = sorted(df[df['Unit'] == sel_unit]['Desk'].unique().astype(str))
            sel_desk = st.selectbox("Desk", d_sort)
        with c3:
            st.write("")
            st.write("")
            if 'show_btn' not in st.session_state: st.session_state.show_btn = False
            if st.button("Show Staff", type="primary", use_container_width=True):
                st.session_state.show_btn = True
                
        if st.session_state.show_btn:
            st.markdown("---")
            subset = df[(df['Unit'] == sel_unit) & (df['Desk'] == sel_desk)]
            
            gc1, gc2 = st.columns([1, 2])
            with gc1:
                if not subset.empty:
                    counts = subset['Status'].value_counts().reset_index()
                    counts.columns = ['Status', 'Count']
                    fig = px.pie(counts, values='Count', names='Status', 
                                 color='Status',
                                 color_discrete_map={'VACANCY':'#ef4444', 'Transferred':'#f97316', 'Active':'#10b981'},
                                 hole=0.4)
                    fig.update_layout(height=250, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig, use_container_width=True)
            
            with gc2:
                st.write(f"**Staff at {sel_unit} - {sel_desk}**")
                if not subset.empty:
                    def highlight(row):
                        if row['Status'] == 'VACANCY': return ['background-color: #fee2e2; color: #991b1b'] * len(row)
                        if row['Status'] == 'Transferred': return ['background-color: #ffedd5; color: #9a3412'] * len(row)
                        return [''] * len(row)
                    st.dataframe(
                        subset[['Staff_Name', 'Status', 'Action_Required']].style.apply(highlight, axis=1),
                        use_container_width=True, 
                        hide_index=True
                    )

# --- PAGE 3: SMART ADMIN EDITOR ---
elif page == "Admin (Smart Editor)":
    st.title("🛠️ Staffing Editor")
    
    pwd = st.text_input("Enter Admin Password", type="password")
    if pwd == "admin123":
        st.success("Unlocked")
        st.info("Select a position below to EDIT it. This will replace the existing person/vacancy.")
        
        # 1. Select Unit and Desk
        c1, c2 = st.columns(2)
        with c1:
            u_in = st.selectbox("Select Unit", df['Unit'].unique())
        with c2:
            d_in = st.selectbox("Select Desk", df[df['Unit'] == u_in]['Desk'].unique())
            
        # 2. Show Existing Rows for this desk
        current_rows = df[(df['Unit'] == u_in) & (df['Desk'] == d_in)]
        
        if not current_rows.empty:
            st.markdown("### Select which position to modify:")
            
            # Create a list of options formatted nicely
            # We use the index to track which row to edit
            options = {}
            for idx, row in current_rows.iterrows():
                label = f"{row['Staff_Name']}  [{row['Status']}]"
                options[label] = idx
            
            selected_label = st.radio("Current Staff List:", list(options.keys()))
            selected_index = options[selected_label]
            
            # 3. Edit Form
            st.markdown("---")
            st.markdown(f"**Editing:** `{selected_label}`")
            
            ec1, ec2 = st.columns(2)
            with ec1:
                # Pre-fill with existing data if not VACANT
                current_val = df.loc[selected_index, 'Staff_Name']
                if "VACANT" in current_val or "Transferred" in current_val:
                    current_val = "" # Clear it for easier typing of new name
                
                new_name = st.text_input("New Person Name", value=current_val, placeholder="Enter Name of new staff")
            
            with ec2:
                new_status = st.selectbox("New Status", ["Active", "Transferred", "VACANCY"])
            
            if st.button("Update Position"):
                # Logic: Update the specific row index
                if new_status == "VACANCY":
                    df.at[selected_index, 'Staff_Name'] = "VACANT POSITION"
                    df.at[selected_index, 'Status'] = "VACANCY"
                    df.at[selected_index, 'Action_Required'] = "Immediate Deployment"
                elif new_status == "Transferred":
                    df.at[selected_index, 'Staff_Name'] = f"{new_name} (Transferred)"
                    df.at[selected_index, 'Status'] = "Transferred"
                    df.at[selected_index, 'Action_Required'] = "Verify Replacement"
                else:
                    df.at[selected_index, 'Staff_Name'] = new_name
                    df.at[selected_index, 'Status'] = "Active"
                    df.at[selected_index, 'Action_Required'] = ""
                
                # Save
                save_data(df)
                st.success("✅ Database Updated! The position has been filled/modified.")
                st.rerun()
                
        else:
            st.warning("No positions found for this desk.")
            # Option to add a new slot if the roster expands?
            if st.button("Add New Slot (Increase Strength)"):
                new_row = {"Unit": u_in, "Desk": d_in, "Staff_Name": "VACANT POSITION", "Status": "VACANCY", "Action_Required": "New Slot Created"}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df)
                st.rerun()
