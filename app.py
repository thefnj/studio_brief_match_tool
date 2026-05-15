import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
from datetime import date

# --- 1. PAGE CONFIG & API ---
st.set_page_config(page_title="Studio Brief Matcher", page_icon="💡", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Gemini API key missing in Secrets.")
    st.stop()

# --- 2. DATA SOURCE (Publish to Web CSV Links) ---
IDEAS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfIYgDs8lnWvKyYR_o7d00KcRdk-Hy1oeOYwYVd5ShDGGBPEO4wcP5ZzQI3ZSX-4j4g1NL1s9fnA-E/pub?gid=1655639181&single=true&output=csv"
COMPONENTS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfIYgDs8lnWvKyYR_o7d00KcRdk-Hy1oeOYwYVd5ShDGGBPEO4wcP5ZzQI3ZSX-4j4g1NL1s9fnA-E/pub?gid=571399293&single=true&output=csv"

@st.cache_data(ttl=300)
def load_live_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), keep_default_na=False)
        for col in df.columns:
            if any(key in col for key in ['Budget', 'Cost']):
                df[col] = df[col].astype(str).str.replace(r'[€, ]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Sheet Load Error: {e}")
        return pd.DataFrame()

# --- 3. AI PRODUCER LOGIC ---
def find_matches(brief, profile, budget, ideas_df, comps_df):
    # 1. DISCOVER MODELS: Let the code find what is available for YOUR key
    try:
        available_models = [m.name for m in genai.list_models()]
        
        # Priority list: Best to oldest
        if any("gemini-1.5-flash" in m for m in available_models):
            target_model = "models/gemini-1.5-flash"
        elif any("gemini-1.5-pro" in m for m in available_models):
            target_model = "models/gemini-1.5-pro"
        else:
            target_model = "models/gemini-pro" # The universal fallback
            
    except Exception as e:
        st.error(f"Discovery failed: {e}")
        target_model = "models/gemini-pro"

    # 2. PREPARE THE DATA
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    
    prompt = f"""
    Find the best idea from this list for this brief: {brief}.
    Budget: €{budget}. Profile: {profile}.
    
    RETURN ONLY JSON with keys: "idea_id", "reason", "selected_components", "total_cost".
    
    IDEAS: {json.dumps(ideas_lean)}
    """
    
    # 3. CALL THE MODEL (Safe for 1.0 and 1.5)
    model = genai.GenerativeModel(target_model)
    
    # We remove 'response_mime_type' here because gemini-pro (1.0) doesn't support it
    # We will handle the JSON cleaning manually to be safe
    response = model.generate_content(prompt)
    
    try:
        # Clean the text in case the AI wraps it in markdown like ```json
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Parsing failed. AI returned: {response.text}")
        return None
        
# --- 4. MAIN UI ---
def main():
    st.title("💡 Studio Brief Matcher")
    
    # Pre-load data
    ideas_df = load_live_data(IDEAS_URL)
    comps_df = load_live_data(COMPONENTS_URL)

    if ideas_df.empty or comps_df.empty:
        st.error("Database connection failed. Please check Google Sheet 'Publish to Web' settings.")
        return

    # --- INPUT CARDS ---
    st.markdown("#### 📝 1. The Brief")
    with st.container(border=True):
        new_brief_text = st.text_area("What is the client looking for?", height=100, label_visibility="collapsed")

    col_left, col_right = st.columns(2)

    with col_left:
        with st.container(border=True):
            st.markdown("#### 👥 2. Target Audience")
            gender = st.radio("Gender Focus:", ["Both", "Male", "Female"], horizontal=True)
            age_ranges = st.multiselect("Age Ranges:", ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"])
            social_status = st.multiselect("Social Status / Life Stage:", ["Students", "Young Professionals", "Parents", "Executives", "Retirees"])

    with col_right:
        with st.container(border=True):
            st.markdown("#### 📊 3. Budget & Media Mix")
            budget_val = st.slider("Max Budget (€):", 5000, 300000, 50000, step=5000, format="€%d")
            media_mix = st.multiselect("Primary Channels:", ["Print", "Digital", "Radio", "Events", "Video", "Social"], default=["Digital"])
            duration = st.number_input("Campaign Duration (Days):", 1, 365, 30)

    # --- EXECUTION ---
    st.markdown("---")
    if st.button("🚀 GENERATE MATCHED PROPOSAL", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please provide a brief description.")
        else:
            with st.spinner("Producer is building your custom package..."):
                profile_summary = f"Gender: {gender}, Ages: {age_ranges}, Status: {social_status}, Mix: {media_mix}, Days: {duration}"
                result = find_matches(new_brief_text, profile_summary, budget_val, ideas_df, comps_df)
                st.session_state.match_result = result

    # --- RESULTS DISPLAY ---
    if 'match_result' in st.session_state:
        res = st.session_state.match_result
        idea = ideas_df[ideas_df['Idea_ID'] == res['idea_id']].iloc[0]
        
        st.header(f"Match: {idea['Generic_idea_title']}")
        st.info(res['reason'])
        
        st.subheader("🛠️ Recommended Component Build")
        selected_comps = comps_df[comps_df['Component_ID'].isin(res['selected_components'])]
        
        # Display as cards
        for _, c in selected_comps.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{c['Component_type']}**")
                c1.write(c['Description'])
                c2.markdown(f"### €{c['Estimated_Budget']:,}")
        
        st.divider()
        st.metric("Total Proposal Value", f"€{res['total_cost']:,}", delta=f"€{budget_val - res['total_cost']:,} under budget")

if __name__ == "__main__":
    main()
