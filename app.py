import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
import re

# --- 1. PAGE CONFIG & API ---
st.set_page_config(page_title="Studio Brief Matcher", page_icon="💡", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Gemini API key missing in Secrets.")
    st.stop()

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

# --- 2. HELPER TO STRIP IDS ---
def clean_id(text):
    """Removes 'IDEA-001' or 'COMP-001' style prefixes from strings."""
    return re.sub(r'^(IDEA|COMP)-\d+\s*:?\s*', '', str(text)).strip()

# --- 3. AI PRODUCER LOGIC ---
def find_matches(brief, profile, total_budget, media_mix, ideas_df, comps_df, model_name):
    # Calculate Media Spend First (10% per selected channel)
    media_items = []
    reserved_media_budget = 0
    percent_per_channel = 0.10 # 10%
    
    for channel in media_mix:
        spend = int(total_budget * percent_per_channel)
        reserved_media_budget += spend
        media_items.append({
            "Component_type": f"{channel} Media Spend",
            "Description": f"Paid media investment/ad spend for {channel} distribution.",
            "Estimated_Budget": spend,
            "is_media_spend": True
        })

    # Available for production after media spend
    production_budget = total_budget - reserved_media_budget

    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are an expert Media Planner. 
    TOTAL CLIENT BUDGET: €{total_budget}
    RESERVED MEDIA SPEND (DO NOT TOUCH): €{reserved_media_budget}
    REMAINING PRODUCTION BUDGET: €{production_budget}

    TASK:
    1. Find the best conceptual match from IDEAS.
    2. Pick Creative Components from the list that total NO MORE THAN €{production_budget}.
    3. Ensure components align with: {media_mix}.

    RETURN ONLY JSON:
    {{
        "idea_id": "ID",
        "reason": "Explain the creative strategy and how the production works with the media spend...",
        "selected_components": ["COMP-001"],
        "production_cost": 45000
    }}
    
    IDEAS: {json.dumps(ideas_lean)}
    COMPONENTS: {json.dumps(comps_lean)}
    """
    
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
        
        # Add the auto-generated media items to the final result
        result['media_items'] = media_items
        result['total_final_cost'] = result['production_cost'] + reserved_media_budget
        return result
    except Exception as e:
        st.error(f"Logic Error: {e}")
        return None

# --- 4. MAIN UI ---
def main():
    st.title("💡 Studio Brief Matcher")
    
    ideas_df = load_live_data(IDEAS_URL)
    comps_df = load_live_data(COMPONENTS_URL)

    with st.sidebar:
        st.header("⚙️ Settings")
        try:
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            default_idx = next((i for i, m in enumerate(all_models) if "gemini-1.5-flash" in m), 0)
            selected_model = st.selectbox("Active AI:", all_models, index=default_idx)
        except:
            selected_model = "models/gemini-1.5-flash"

    # --- INPUT CARDS ---
    st.markdown("#### 📝 1. The Brief")
    with st.container(border=True):
        new_brief_text = st.text_area("What is the client looking for?", height=100, label_visibility="collapsed")

    col_left, col_right = st.columns(2)
    with col_left:
        with st.container(border=True):
            st.markdown("#### 👥 2. Target Audience")
            gender = st.radio("Gender:", ["Both", "Male", "Female"], horizontal=True)
            age_options = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
            age_ranges = st.multiselect("Age Ranges:", age_options, default=age_options)

    with col_right:
        with st.container(border=True):
            st.markdown("#### 📊 3. Budget & Media Mix")
            budget_val = st.slider("Total Budget (€):", 5000, 300000, 100000, step=5000, format="€%d")
            channel_options = ["Print", "Digital", "Radio", "Events", "Video", "Social"]
            media_mix = st.multiselect("Channels:", channel_options, default=channel_options)
            duration = st.number_input("Campaign Duration (Days):", 1, 365, 30)

    # --- EXECUTION ---
    if st.button("🚀 GENERATE PROPOSAL", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please enter brief details.")
        else:
            with st.spinner("Calculating media split and production costs..."):
                profile_summary = f"Gender: {gender}, Ages: {age_ranges}, Mix: {media_mix}"
                result = find_matches(new_brief_text, profile_summary, budget_val, media_mix, ideas_df, comps_df, selected_model)
                st.session_state.match_result = result

    # --- RESULTS ---
    if 'match_result' in st.session_state and st.session_state.match_result:
        res = st.session_state.match_result
        matched_idea_df = ideas_df[ideas_df['Idea_ID'] == res['idea_id']]
        
        if not matched_idea_df.empty:
            idea = matched_idea_df.iloc[0]
            # CLEANED TITLE (No IDEA-001)
            st.header(f"Strategy: {clean_id(idea['Generic_idea_title'])}")
            st.info(res['reason'])
            
            # --- SHOW MEDIA SPEND FIRST ---
            st.subheader("📢 Allocated Media Buy (10% per channel)")
            m_cols = st.columns(len(res['media_items']))
            for i, m_item in enumerate(res['media_items']):
                with m_cols[i]:
                    st.metric(m_item['Component_type'], f"€{m_item['Estimated_Budget']:,}")

            # --- SHOW PRODUCTION COMPONENTS ---
            st.subheader("🛠️ Creative Production Build")
            selected_comps = comps_df[comps_df['Component_ID'].isin(res['selected_components'])]
            for _, c in selected_comps.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**{clean_id(c['Component_type'])}**") # CLEANED
                    c1.write(c['Description'])
                    c2.markdown(f"### €{c['Estimated_Budget']:,}")
            
            st.divider()
            col1, col2, col3 = st.columns(3)
            col1.metric("Production Subtotal", f"€{res['production_cost']:,}")
            col2.metric("Media Buy Subtotal", f"€{res['total_final_cost'] - res['production_cost']:,}")
            col3.metric("Total Proposal Value", f"€{res['total_final_cost']:,}", delta=f"€{budget_val - res['total_final_cost']:,} under budget")
        else:
            st.error("AI matched an ID not in the sheet.")

if __name__ == "__main__":
    main()
