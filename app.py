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

# --- 2. DATA SOURCE ---
# Using your specific GIDs from your last message
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
def find_matches(brief, profile, budget, ideas_df, comps_df, model_name):
    # 1. Prepare lean data - including Component_type is key here
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary', 'Channels']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are an expert Media Planner and Creative Producer.
    
    USER BRIEF: {brief}
    MEDIA MIX & PROFILE: {profile}
    MAX BUDGET: €{budget}

    TASK:
    1. Find the best conceptual match from IDEAS.
    2. Build a proposal using ONLY components from that Idea that align with the requested Media Mix.
    
    CHANNEL MAPPING RULES:
    - If 'Radio' is in the Mix, prioritize 'Radio Commercial Series' or 'Radio' components.
    - If 'Digital' is in the Mix, include 'Video', 'Social', 'Branded Article', or 'Digital' components.
    - If 'Video' is in the Mix, include 'Video Series' or 'VOD'.
    - If 'Print' is in the Mix, include 'Editorial', 'Press', or 'Advertorial'.
    - If 'Events' is in the Mix, include 'Live Event' or 'Experiential'.

    BUDGET RULE: The sum of 'Estimated_Budget' for selected components MUST be under €{budget}.

    RETURN ONLY JSON:
    {{
        "idea_id": "ID",
        "reason": "Explain how this concept fits the brief AND how the components satisfy the {profile} media mix requirements...",
        "selected_components": ["COMP-001", "COMP-002"],
        "total_cost": 50000
    }}
    
    IDEAS: {json.dumps(ideas_lean)}
    COMPONENTS: {json.dumps(comps_lean)}
    """
    
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Logic Error: {e}")
        return None

# --- 4. MAIN UI ---
def main():
    st.title("💡 Studio Brief Matcher")
    
    # Pre-load data
    ideas_df = load_live_data(IDEAS_URL)
    comps_df = load_live_data(COMPONENTS_URL)

    # --- MODEL SELECTOR SIDEBAR (The Safety Net) ---
    with st.sidebar:
        st.header("⚙️ Model Settings")
        try:
            # Dynamically fetch every model your key is allowed to use
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            # Select 2.5 Flash if it exists, otherwise 1.5, otherwise first in list
            default_idx = 0
            for i, m in enumerate(all_models):
                if "gemini-2.5-flash" in m: default_idx = i; break
                elif "gemini-1.5-flash" in m: default_idx = i; break

            selected_model = st.selectbox("Select Active AI Model:", all_models, index=default_idx)
            st.success(f"Using: {selected_model}")
            
        except Exception as e:
            st.error(f"Could not list models: {e}")
            selected_model = "models/gemini-pro" # Hard fallback

    if ideas_df.empty or comps_df.empty:
        st.error("Database connection failed. Please check Google Sheet 'Publish to Web' settings.")
        return

# --- UPDATED INPUT CARDS ---
    st.markdown("#### 📝 1. The Brief")
    with st.container(border=True):
        new_brief_text = st.text_area("What is the client looking for?", height=100, label_visibility="collapsed")

    col_left, col_right = st.columns(2)
    with col_left:
        with st.container(border=True):
            st.markdown("#### 👥 2. Target Audience")
            gender = st.radio("Gender Focus:", ["Both", "Male", "Female"], horizontal=True)
            
            # AGE RANGES: Pre-populated so you can 'X' them off
            age_options = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
            age_ranges = st.multiselect(
                "Age Ranges:", 
                options=age_options, 
                default=age_options # All selected by default
            )

    with col_right:
        with st.container(border=True):
            st.markdown("#### 📊 3. Budget & Media Mix")
            # Budget set to 100k default
            budget_val = st.slider("Max Budget (€):", 5000, 300000, 100000, step=5000, format="€%d")
            
            # PRIMARY CHANNELS: Pre-populated so you can 'X' them off
            channel_options = ["Print", "Digital", "Radio", "Events", "Video", "Social"]
            media_mix = st.multiselect(
                "Primary Channels:", 
                options=channel_options, 
                default=channel_options # All selected by default
            )
            
            duration = st.number_input("Campaign Duration (Days):", 1, 365, 30)

    # --- UPDATED EXECUTION LOGIC (Removed Social Status) ---
    st.markdown("---")
    if st.button("🚀 GENERATE MATCHED PROPOSAL", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please provide a brief description.")
        else:
            with st.spinner(f"AI Producer ({selected_model}) is thinking..."):
                # Updated profile_summary string (no more status)
                # Update this line inside the 'if st.button' block:
                profile_summary = f"TARGET AUDIENCE: {gender} {age_ranges}. REQUIRED MEDIA MIX: {media_mix}. DURATION: {duration} days."
                result = find_matches(new_brief_text, profile_summary, budget_val, ideas_df, comps_df, selected_model)
                st.session_state.match_result = result

    # --- RESULTS DISPLAY ---
    if 'match_result' in st.session_state and st.session_state.match_result:
        res = st.session_state.match_result
        # Logic to find the matched idea
        matched_idea_df = ideas_df[ideas_df['Idea_ID'] == res['idea_id']]
        
        if not matched_idea_df.empty:
            idea = matched_idea_df.iloc[0]
            st.header(f"Match: {idea['Generic_idea_title']}")
            st.info(res['reason'])
            
            st.subheader("🛠️ Recommended Component Build")
            selected_comps = comps_df[comps_df['Component_ID'].isin(res['selected_components'])]
            
            for _, c in selected_comps.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**{c['Component_type']}**")
                    c1.write(c['Description'])
                    c2.markdown(f"### €{c['Estimated_Budget']:,}")
            
            st.divider()
            st.metric("Total Proposal Value", f"€{res['total_cost']:,}", delta=f"€{budget_val - res['total_cost']:,} under budget")
        else:
            st.error(f"AI matched ID '{res['idea_id']}' which was not found in your Ideas sheet.")

if __name__ == "__main__":
    main()
