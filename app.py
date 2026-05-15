import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
from datetime import date

# --- Page Configuration ---
st.set_page_config(page_title="Brief Matcher 2.0", page_icon="💡", layout="wide")

# --- API Setup ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Gemini API key not found. Please add it to Streamlit Secrets.")
    st.stop()

# --- CONSTANTS (Corrected Export Links) ---
# Note: I've updated these to the /export?format=csv format
IDEAS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfIYgDs8lnWvKyYR_o7d00KcRdk-Hy1oeOYwYVd5ShDGGBPEO4wcP5ZzQI3ZSX-4j4g1NL1s9fnA-E/pub?gid=1655639181&single=true&output=csv"
COMPONENTS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfIYgDs8lnWvKyYR_o7d00KcRdk-Hy1oeOYwYVd5ShDGGBPEO4wcP5ZzQI3ZSX-4j4g1NL1s9fnA-E/pub?gid=571399293&single=true&output=csv"

# --- 1. DATA LOADING FUNCTION ---
@st.cache_data(ttl=600)
def load_live_data(url):
    """Fetches Google Sheet data and cleans budget columns."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), keep_default_na=False)
        
        # Clean Budget Columns (Removes €, commas, and whitespace)
        for col in df.columns:
            if 'Budget' in col or 'Cost' in col:
                df[col] = df[col].astype(str).str.replace(r'[€, ]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# --- 2. MATCHING LOGIC ---
def find_matches(new_brief, params, user_budget, ideas_df, comps_df):
    """Sends prompt to Gemini and returns JSON match data."""
    ideas_json = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary', 'Budget_band', 'Target_audience', 'Original_sector']].to_dict('records')
    comps_json = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Strategic Producer. 
    1. Match the brief to the best CONCEPT from the IDEAS list.
    2. Build a custom package using COMPONENTS linked to that Idea (via Parent_Idea_ID).
    3. Ensure the total 'Estimated_Budget' is under €{user_budget}.

    NEW BRIEF: {new_brief}
    USER FILTERS: {params}
    CLIENT BUDGET: €{user_budget}

    IDEAS LIBRARY: {json.dumps(ideas_json)}
    COMPONENTS LIBRARY: {json.dumps(comps_json)}

    RETURN ONLY JSON:
    {{
        "matched_idea_id": "ID here",
        "reasoning": "Brief explanation of why this fits the budget and brief...",
        "selected_component_ids": ["COMP-001", "COMP-002"],
        "total_cost": 45000
    }}
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(res.text)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- 3. MAIN APPLICATION ---
def main():
    st.title("💡 Studio Brief Matcher")
    st.markdown("---")
    
    # LOAD DATA
    ideas_df = load_live_data(IDEAS_URL)
    comps_df = load_live_data(COMPONENTS_URL)

    if ideas_df.empty or comps_df.empty:
        st.warning("Could not load data from Google Sheets. Check your URLs and 'Publish to Web' settings.")
        return

# --- UPDATED INPUT SECTION ---
    st.subheader("1. Campaign & Audience Profile")
    col_a, col_b = st.columns([2, 1])
    
    with col_a:
        new_brief_text = st.text_area(
            "Campaign Details / Brief:", 
            height=150, 
            placeholder="Paste the core client requirements here...",
            help="This is the main text the AI will analyze for creative matching."
        )
        
        # --- Target Audience Categorization ---
        st.markdown("### Target Audience")
        inner_col1, inner_col2 = st.columns(2)
        
        with inner_col1:
            gender = st.radio("Gender:", ["Both", "Male", "Female"], horizontal=True)
            age_ranges = st.multiselect(
                "Age Ranges:", 
                ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
            )
            
        with inner_col2:
            social_status = st.multiselect(
                "Social Status / Life Stage:",
                ["Students", "Young Professionals", "Parents", "Middle Management", "Executives", "Retirees", "High Net Worth"]
            )

    with col_b:
        # --- Budget & Media Mix ---
        st.markdown("### Budget & Media Mix")
        budget_value = st.slider("Available Budget (€):", 5000, 300000, 50000, step=5000)
        
        media_mix = st.multiselect(
            "Required Media Mix:", 
            options=["Print", "Digital", "Radio", "Events", "Video", "Social"],
            default=["Digital", "Social"],
            help="The AI will prioritize components that match these channels."
        )
        
        duration = st.number_input("Campaign Duration (Days):", 1, 365, 30)

    # --- UPDATED ACTION BUTTON ---
    if st.button("🚀 Find Best Match", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please enter some campaign details first!")
        else:
            with st.spinner("Analyzing audience profile and media mix..."):
                # We package all these new inputs into a string for the AI to read
                params = f"""
                AUDIENCE PROFILE:
                - Gender: {gender}
                - Ages: {', '.join(age_ranges)}
                - Status: {', '.join(social_status)}
                
                MEDIA MIX REQUIREMENTS:
                - Channels: {', '.join(media_mix)}
                - Duration: {duration} days
                """
                
                match_result = find_matches(new_brief_text, params, budget_value, ideas_df, comps_df)
                st.session_state.match = match_result

    # --- RESULTS DISPLAY ---
    if 'match' in st.session_state and st.session_state.match:
        st.divider()
        m = st.session_state.match
        
        # Get the full Idea details
        matched_idea = ideas_df[ideas_df['Idea_ID'] == m['matched_idea_id']]
        
        if not matched_idea.empty:
            idea_row = matched_idea.iloc[0]
            st.header(f"Match: {idea_row['Generic_idea_title']}")
            st.info(m['reasoning'])
            
            st.subheader("🛠️ Recommended Component Build")
            # Filter components that the AI chose
            selected_comps = comps_df[comps_df['Component_ID'].isin(m['selected_component_ids'])]
            
            for _, c in selected_comps.iterrows():
                with st.expander(f"**{c['Component_type']}** — €{c['Estimated_Budget']:,}", expanded=True):
                    st.write(c['Description'])
            
            st.metric("Total Proposal Cost", f"€{m['total_cost']:,}", 
                      delta=f"Remaining Budget: €{budget_value - m['total_cost']:,}")
        else:
            st.error("AI matched an ID that doesn't exist in the sheet. Please try again.")

if __name__ == "__main__":
    main()
