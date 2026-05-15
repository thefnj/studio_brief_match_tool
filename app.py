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

def clean_id(text):
    """Removes IDEA-001/COMP-001 prefixes for a cleaner UI."""
    return re.sub(r'^(IDEA|COMP)-\d+\s*:?\s*', '', str(text)).strip()

# --- 2. THE LOGIC ENGINE ---
def find_matches(brief, profile, total_budget, media_mix, ideas_df, comps_df, model_name):
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Senior Strategic Producer. 
    TOTAL BUDGET: €{total_budget}
    REQUIRED MEDIA MIX: {media_mix}

    TASK:
    1. Select the best Idea from the IDEAS list.
    2. Select PRODUCTION COMPONENTS from the COMPONENTS list that fit the budget.
    3. Ensure components align with the brief objectives.

    RETURN JSON:
    {{
        "idea_id": "ID",
        "reason": "Strategy summary...",
        "selected_components": ["COMP-001", "COMP-002"],
        "production_total": 45000
    }}
    
    IDEAS: {json.dumps(ideas_lean)}
    COMPONENTS: {json.dumps(comps_lean)}
    """
    
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
        
        # --- SMART DEDUPLICATION LOGIC ---
        # Get the actual data for the components the AI picked
        prod_data = comps_df[comps_df['Component_ID'].isin(result['selected_components'])]
        
        # We check which channels are already "Produced"
        # We look at the Component_type and the Description for keywords
        produced_channels = []
        for _, row in prod_data.iterrows():
            comp_info = (row['Component_type'] + " " + row['Description']).lower()
            produced_channels.append(comp_info)

        media_gap_items = []
        media_total = 0
        
        # Professional Sales Terms for Gaps
        media_map = {
            "Digital": ("High-impact Digital Display & Programmatic", "Reach targeted audiences across premium web inventory."),
            "Social": ("Targeted Social Media Amplification", "Paid seeding and boosted story placements to drive engagement."),
            "Radio": ("Premium Audio Spot Placement", "High-frequency spot rotation across digital and terrestrial audio."),
            "Print": ("National Press & Editorial Buy", "Full-page placements and contextually relevant advertorials."),
            "Video": ("VOD & YouTube TrueView Ad Spend", "Strategic video sequencing to maximize completion rates."),
            "Events": ("Experiential Promotion & Local Media", "Localized ad support to drive footfall to the physical activation.")
        }

        for channel in media_mix:
            # If the channel isn't mentioned in the production components, add it as media spend
            already_covered = any(channel.lower() in info for info in produced_channels)
            
            if not already_covered:
                spend = int(total_budget * 0.10) # Default 10% for the gap
                media_total += spend
                title, desc = media_map.get(channel, (f"{channel} Media", "Standard media investment."))
                media_gap_items.append({"title": title, "desc": desc, "cost": spend})

        result['media_gaps'] = media_gap_items
        result['final_proposal_total'] = result['production_total'] + media_total
        return result
    except Exception as e:
        st.error(f"Logic Error: {e}")
        return None

# --- 3. THE UI ---
def main():
    st.title("💡 Studio Brief Matcher")
    
    ideas_df = load_live_data(IDEAS_URL)
    comps_df = load_live_data(COMPONENTS_URL)

    with st.sidebar:
        st.header("⚙️ Settings")
        try:
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            def_idx = next((i for i, m in enumerate(all_models) if "flash" in m), 0)
            selected_model = st.selectbox("Active AI Model:", all_models, index=def_idx)
        except:
            selected_model = "models/gemini-1.5-flash"

    # --- INPUTS ---
    st.markdown("#### 📝 1. The Brief")
    with st.container(border=True):
        new_brief_text = st.text_area("What is the client looking for?", height=100, label_visibility="collapsed")

    col_left, col_right = st.columns(2)
    with col_left:
        with st.container(border=True):
            st.markdown("#### 👥 2. Target Audience")
            gender = st.radio("Gender Focus:", ["Both", "Male", "Female"], horizontal=True)
            age_opts = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
            age_ranges = st.multiselect("Age Ranges:", age_opts, default=age_opts)

    with col_right:
        with st.container(border=True):
            st.markdown("#### 📊 3. Budget & Media Mix")
            budget_val = st.slider("Total Budget (€):", 5000, 300000, 100000, step=5000, format="€%d")
            chan_opts = ["Print", "Digital", "Radio", "Events", "Video", "Social"]
            media_mix = st.multiselect("Primary Channels:", chan_opts, default=chan_opts)
            duration = st.number_input("Campaign Duration (Days):", 1, 365, 30)

    # --- ACTION ---
    if st.button("🚀 GENERATE PROPOSAL", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please provide brief details.")
        else:
            with st.spinner("Producer is calculating proposal..."):
                profile = f"Audience: {gender}, {age_ranges}. Mix: {media_mix}."
                res = find_matches(new_brief_text, profile, budget_val, media_mix, ideas_df, comps_df, selected_model)
                st.session_state.match_result = res

    # --- RESULTS DISPLAY ---
    if 'match_result' in st.session_state and st.session_state.match_result:
        res = st.session_state.match_result
        
        # Robust lookup of the Idea
        idea_match = ideas_df[ideas_df['Idea_ID'] == res['idea_id']]
        if not idea_match.empty:
            idea = idea_match.iloc[0]
            st.header(f"Strategy: {clean_id(idea['Generic_idea_title'])}")
            st.info(res['reason'])
            
            st.subheader("📋 Creative Proposal")
            
            # 1. Show the Production Components the AI picked
            selected_comps = comps_df[comps_df['Component_ID'].isin(res['selected_components'])]
            for _, c in selected_comps.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**{clean_id(c['Component_type'])}**")
                    c1.write(c['Description'])
                    c2.markdown(f"### €{c['Estimated_Budget']:,}")

            # 2. Show the "Working Media" Gap-fillers
            for m in res['media_gaps']:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**{m['title']}**")
                    c1.write(m['desc'])
                    c2.markdown(f"### €{m['cost']:,}")
            
            st.divider()
            st.metric("Total Proposal Value", f"€{res['final_proposal_total']:,}", 
                      delta=f"€{budget_val - res['final_proposal_total']:,} remaining")
        else:
            st.error("AI matched an ID not in the database. Please try again.")

if __name__ == "__main__":
    main()
