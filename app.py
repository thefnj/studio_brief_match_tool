import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
import re

# --- 1. PAGE CONFIG & API ---
st.set_page_config(page_title="Studio Brief Matcher", page_icon="💡", layout="wide")

# API Setup with Secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Gemini API key missing in Streamlit Secrets.")
    st.stop()

# --- 2. DATA SOURCE (Publish to Web CSV Links) ---
IDEAS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfIYgDs8lnWvKyYR_o7d00KcRdk-Hy1oeOYwYVd5ShDGGBPEO4wcP5ZzQI3ZSX-4j4g1NL1s9fnA-E/pub?gid=1655639181&single=true&output=csv"
COMPONENTS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfIYgDs8lnWvKyYR_o7d00KcRdk-Hy1oeOYwYVd5ShDGGBPEO4wcP5ZzQI3ZSX-4j4g1NL1s9fnA-E/pub?gid=571399293&single=true&output=csv"

@st.cache_data(ttl=300)
def load_live_data(url):
    """Fetches Google Sheet data and cleans budget columns."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), keep_default_na=False)
        # Clean Budget Columns automatically
        for col in df.columns:
            if any(key in col for key in ['Budget', 'Cost']):
                df[col] = df[col].astype(str).str.replace(r'[€, ]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Sheet Load Error: {e}")
        return pd.DataFrame()

def clean_label(text):
    """Removes 'IDEA-001' or 'COMP-001' style prefixes from strings for a clean UI."""
    return re.sub(r'^(IDEA|COMP)-\d+\s*:?\s*', '', str(text)).strip()

# --- 3. AI PRODUCER & BUDGETING LOGIC ---
def find_matches(brief, profile, total_budget, media_mix, ideas_df, comps_df, model_name):
    # Prepare data for AI
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Senior Strategic Producer. 
    TOTAL BUDGET: €{total_budget}
    REQUIRED MEDIA MIX: {media_mix}

    TASK:
    1. Select the best Idea from the IDEAS list based on the brief.
    2. Select PRODUCTION COMPONENTS from the COMPONENTS list (linked by Parent_Idea_ID).
    3. Ensure production costs leave significant room for media spend.
    
    RETURN ONLY JSON:
    {{
        "idea_id": "ID",
        "reason": "Explain the strategy and why this fits the {media_mix} mix...",
        "selected_components": ["COMP-001", "COMP-002"]
    }}
    
    IDEAS: {json.dumps(ideas_lean)}
    COMPONENTS: {json.dumps(comps_lean)}
    """
    
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
        
        # --- ZERO-WASTE BUDGET REDISTRIBUTION (The Python Math) ---
        # 1. Calculate Creative Production Subtotal
        prod_data = comps_df[comps_df['Component_ID'].isin(result['selected_components'])]
        production_total = prod_data['Estimated_Budget'].sum()
        
        # 2. Identify Media Gaps (Channels selected but NOT covered by production)
        produced_types = [str(t).lower() for t in prod_data['Component_type'].unique()]
        media_gaps = [c for c in media_mix if not any(c.lower() in t for t in produced_types)]
        
        # 3. Calculate Remainder and Split it across Gaps
        remaining_budget = total_budget - production_total
        
        media_items = []
        if media_gaps and remaining_budget > 0:
            spend_per_gap = int(remaining_budget / len(media_gaps))
            
            # Professional Media Descriptors
            media_map = {
                "Digital": ("High-impact Digital Display & Programmatic", "Targeted reach across premium web inventory."),
                "Social": ("Targeted Social Media Amplification", "Paid seeding and boosted story placements to drive engagement."),
                "Radio": ("Premium Audio Spot Placement", "High-frequency spot rotation across digital and terrestrial audio."),
                "Print": ("National Press & Editorial Buy", "Full-page placements and contextually relevant advertorials."),
                "Video": ("VOD & YouTube TrueView Ad Spend", "Strategic video sequencing to maximize completion rates."),
                "Events": ("Experiential Promotion & Local Media", "Localized ad support to drive footfall to the physical activation.")
            }

            for channel in media_gaps:
                title, desc = media_map.get(channel, (f"{channel} Working Media", "Standard media investment."))
                media_items.append({
                    "title": title,
                    "desc": desc,
                    "cost": spend_per_gap
                })
        
        # Package results for UI
        result['production_items_data'] = prod_data.to_dict('records')
        result['media_items_data'] = media_items
        result['grand_total'] = production_total + (sum(m['cost'] for m in media_items))
        return result
        
    except Exception as e:
        st.error(f"Logic Error: {e}")
        return None

# --- 4. MAIN UI ---
def main():
    st.title("💡 Studio Brief Matcher")
    
    # Pre-load data
    ideas_df = load_live_data(IDEAS_URL)
    comps_df = load_live_data(COMPONENTS_URL)

    # --- MODEL SELECTOR (Safety Sidebar) ---
    with st.sidebar:
        st.header("⚙️ Settings")
        try:
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            def_idx = next((i for i, m in enumerate(all_models) if "flash" in m), 0)
            selected_model = st.selectbox("Active AI Model:", all_models, index=def_idx)
        except:
            selected_model = "models/gemini-1.5-flash"
        
        if st.button("Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    if ideas_df.empty or comps_df.empty:
        st.error("Database connection failed. Check Google Sheets 'Publish to Web' settings.")
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
            
            # AGE RANGES: Pre-populated so user can 'X' them off
            age_options = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
            age_ranges = st.multiselect("Age Ranges:", age_options, default=age_options)

    with col_right:
        with st.container(border=True):
            st.markdown("#### 📊 3. Budget & Media Mix")
            # Default set to 100,000
            budget_val = st.slider("Total Budget (€):", 5000, 300000, 100000, step=5000, format="€%d")
            
            # CHANNELS: Pre-populated so user can 'X' them off
            chan_options = ["Print", "Digital", "Radio", "Events", "Video", "Social"]
            media_mix = st.multiselect("Primary Channels:", chan_opts, default=chan_options)
            
            duration = st.number_input("Campaign Duration (Days):", 1, 365, 30)

    # --- EXECUTION ---
    st.markdown("---")
    if st.button("🚀 GENERATE PROPOSAL", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please provide a brief description.")
        else:
            with st.spinner("Optimizing budget across creative and media..."):
                profile = f"Audience: {gender}, {age_ranges}. Mix: {media_mix}."
                res = find_matches(new_brief_text, profile, budget_val, media_mix, ideas_df, comps_df, selected_model)
                st.session_state.match_result = res

    # --- RESULTS DISPLAY ---
    if 'match_result' in st.session_state and st.session_state.match_result:
        res = st.session_state.match_result
        
        # Look up original Idea details
        idea_match = ideas_df[ideas_df['Idea_ID'] == res['idea_id']]
        if not idea_match.empty:
            idea = idea_match.iloc[0]
            st.header(f"Strategy: {clean_label(idea['Generic_idea_title'])}")
            st.info(res['reason'])
            
            st.subheader("📋 Creative Proposal")
            
            # 1. SHOW PRODUCTION COMPONENTS FIRST
            for item in res['production_items_data']:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**🛠️ {clean_label(item['Component_type'])}**")
                    c1.write(item['Description'])
                    c2.markdown(f"### €{item['Estimated_Budget']:,}")

            # 2. SHOW THE "TOPPED UP" MEDIA GAPS SECOND
            for m in res['media_items_data']:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**📢 {m['title']}**")
                    c1.write(m['desc'])
                    c2.markdown(f"### €{m['cost']:,}")
            
            st.divider()
            # Final calculation metrics
            st.metric("Total Proposal Value", f"€{res['grand_total']:,}", 
                      delta="Budget fully utilized" if res['grand_total'] >= budget_val else f"€{budget_val - res['grand_total']:,} remaining")
        else:
            st.error("The AI matched an ID that doesn't exist in the database. Please try again.")

if __name__ == "__main__":
    main()
