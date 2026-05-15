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
    st.error("Gemini API key missing.")
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

def clean_label(text):
    """Strips IDEA-001 and COMP-001 prefixes for a clean UI."""
    return re.sub(r'^(IDEA|COMP)-\d+\s*:?\s*', '', str(text)).strip()

# --- 2. THE LOGIC ENGINE ---
def find_matches(brief, profile, total_budget, media_mix, ideas_df, comps_df, model_name):
    # Professional Media Spend Mapping
    media_spend_map = {
        "Digital": "High-impact Digital Display & Programmatic Media Buy",
        "Social": "Targeted Social Media Amplification & Paid Seeding",
        "Radio": "Premium Spot Placement & Digital Audio Inventory",
        "Print": "National Press Placements & Niche Editorial Media Buy",
        "Video": "VOD & YouTube TrueView Ad Sequencing",
        "Events": "Experiential Promotion & Local Media Support"
    }
    
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Senior Strategic Producer. 
    TOTAL BUDGET: €{total_budget}
    REQUIRED CHANNELS: {media_mix}

    STRICT BUDGET RULES:
    1. The TOTAL sum of all Production Components + all Working Media Spend MUST NOT exceed €{total_budget}.
    2. For every channel in {media_mix} that is NOT covered by a production component, you MUST allocate exactly 10% of the total budget (€{int(total_budget * 0.1)}) to 'Working Media'.
    3. If a production component already covers a channel (e.g., 'Radio Commercials'), do NOT add the 10% media spend for that channel.

    TASK:
    - Pick the best Idea.
    - Select the best Components.
    - Calculate the remaining gaps and include them as "Working Media" items using these terms: {list(media_spend_map.values())}.

    RETURN JSON:
    {{
        "idea_id": "ID",
        "reason": "Strategy summary...",
        "proposal_items": [
            {{ "title": "Item Title", "desc": "Item Description", "cost": 5000, "is_media": false }},
            {{ "title": "Media Buy Title", "desc": "Placement description", "cost": 10000, "is_media": true }}
        ],
        "grand_total": 95000
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
            with st.spinner("Producer is calculating creative proposal..."):
                profile = f"Audience: {gender}, {age_ranges}. Mix: {media_mix}."
                res = find_matches(new_brief_text, profile, budget_val, media_mix, ideas_df, comps_df, selected_model)
                st.session_state.match_result = res

    # --- RESULTS DISPLAY ---
    if 'match_result' in st.session_state and st.session_state.match_result:
        res = st.session_state.match_result
        
        idea_match = ideas_df[ideas_df['Idea_ID'] == res['idea_id']]
        if not idea_match.empty:
            idea = idea_match.iloc[0]
            st.header(f"Strategy: {clean_label(idea['Generic_idea_title'])}")
            st.info(res['reason'])
            
            st.subheader("📋 Creative Proposal")
            
            # Unified display for both Production and Media items
            for item in res['proposal_items']:
                # Set a color accent for media spend vs production
                border_color = "blue" if item.get('is_media') else "none"
                
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    title_prefix = "📢 " if item.get('is_media') else "🛠️ "
                    c1.markdown(f"**{title_prefix}{clean_label(item['title'])}**")
                    c1.write(item['desc'])
                    c2.markdown(f"### €{item['cost']:,}")
            
            st.divider()
            st.metric("Total Proposal Value", f"€{res['grand_total']:,}", 
                      delta=f"€{budget_val - res['grand_total']:,} under budget")
        else:
            st.error("AI matched an ID not in the database. Please try again.")

if __name__ == "__main__":
    main()
