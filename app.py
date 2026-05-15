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
import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
import re

# ... (Keep Imports, Page Config, and Load Data functions as they were) ...

def clean_id(text):
    return re.sub(r'^(IDEA|COMP)-\d+\s*:?\s*', '', str(text)).strip()

def find_matches(brief, profile, total_budget, media_mix, ideas_df, comps_df, model_name):
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Senior Strategic Producer. 
    
    TOTAL BUDGET: €{total_budget}
    REQUIRED CHANNELS: {media_mix}

    TASK:
    1. Select the best Idea and the best Creative Components (Parent_Idea_ID) from the library.
    2. Budget for these production items first.
    3. Return the JSON.

    RETURN JSON:
    {{
        "idea_id": "ID",
        "reason": "Strategy summary...",
        "selected_components": ["COMP-001"],
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
        
        # --- SMART MEDIA SPEND LOGIC ---
        production_items = comps_df[comps_df['Component_ID'].isin(result['selected_components'])]
        # Identify which channels are ALREADY covered by production
        covered_channels = [str(c).lower() for c in production_items['Component_type'].unique()]
        
        working_media_items = []
        media_total = 0
        
        # Professional naming map
        media_descriptors = {
            "Digital": "High-impact Digital Display & Programmatic Media Buy",
            "Social": "Targeted Social Media Amplification & Paid Seeding",
            "Radio": "Premium Spot Placement & Digital Audio Inventory",
            "Print": "National Press Placements & Niche Editorial Media Buy",
            "Video": "VOD & YouTube TrueView Ad Sequencing",
            "Events": "Experiential Media Support & Local Promotion"
        }

        for channel in media_mix:
            # Check if this channel is already in the production components
            is_covered = any(channel.lower() in c for c in covered_channels)
            
            if not is_covered:
                spend = int(total_budget * 0.10)
                media_total += spend
                working_media_items.append({
                    "type": channel,
                    "title": media_descriptors.get(channel, f"{channel} Working Media"),
                    "desc": f"Direct media investment to drive reach and frequency for the campaign across {channel} platforms.",
                    "cost": spend
                })

        result['working_media'] = working_media_items
        result['final_total'] = result['production_total'] + media_total
        return result
    except Exception as e:
        st.error(f"Logic Error: {e}")
        return None

# --- UI DISPLAY SECTION (Inside main) ---
def main():
    # ... (Keep Input Section same as before) ...

    # --- RESULTS ---
    if 'match_result' in st.session_state and st.session_state.match_result:
        res = st.session_state.match_result
        idea = ideas_df[ideas_df['Idea_ID'] == res['idea_id']].iloc[0]
        
        st.header(f"Strategy: {clean_id(idea['Generic_idea_title'])}")
        st.info(res['reason'])
        
        st.subheader("📋 Creative Proposal")
        
        # 1. Show Production Components from DB
        selected_comps = comps_df[comps_df['Component_ID'].isin(res['selected_components'])]
        for _, c in selected_comps.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{clean_id(c['Component_type'])}**")
                c1.write(c['Description'])
                c2.markdown(f"### €{c['Estimated_Budget']:,}")

        # 2. Show the "Gap-filling" Working Media
        for m in res['working_media']:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                # Show professional sales term as the title
                c1.markdown(f"**{m['title']}**")
                c1.write(m['desc'])
                c2.markdown(f"### €{m['cost']:,}")
        
        st.divider()
        col1, col2 = st.columns(2)
        col1.metric("Total Proposal Value", f"€{res['final_total']:,}", delta=f"€{budget_val - res['final_total']:,} remaining")
        col2.write("Includes all creative production, licensing, and strategic media allocation as detailed above.")

if __name__ == "__main__":
    main()
