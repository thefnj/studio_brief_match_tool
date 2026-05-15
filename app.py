import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
import re

# ... (Keep Imports, Page Config, and load_live_data functions as they were) ...

def clean_label(text):
    """Strips IDEA-001 and COMP-001 prefixes."""
    return re.sub(r'^(IDEA|COMP)-\d+\s*:?\s*', '', str(text)).strip()

# --- 2. THE REFINED LOGIC ENGINE ---
def find_matches(brief, profile, total_budget, media_mix, ideas_df, comps_df, model_name):
    ideas_lean = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary']].to_dict('records')
    comps_lean = comps_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Senior Strategic Producer. 
    TOTAL BUDGET: €{total_budget}
    REQUIRED CHANNELS: {media_mix}

    TASK:
    1. Select the best Idea from the IDEAS list.
    2. Select the best PRODUCTION COMPONENTS from the COMPONENTS list.
    3. Ensure production costs leave room for media spend.
    
    RETURN JSON:
    {{
        "idea_id": "ID",
        "reason": "Strategy summary...",
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
        
        # --- SMART BUDGET REDISTRIBUTION ---
        # 1. Calculate actual production total
        prod_data = comps_df[comps_df['Component_ID'].isin(result['selected_components'])]
        production_total = prod_data['Estimated_Budget'].sum()
        
        # 2. Identify Gaps
        produced_types = [str(t).lower() for t in prod_data['Component_type'].unique()]
        media_gaps = [c for c in media_mix if not any(c.lower() in t for t in produced_types)]
        
        # 3. Calculate Remainder
        remaining_budget = total_budget - production_total
        
        media_items = []
        if media_gaps:
            # Split the remainder EQUALLY across all gaps
            spend_per_gap = int(remaining_budget / len(media_gaps))
            
            media_map = {
                "Digital": ("High-impact Digital Display & Programmatic", "Reach targeted audiences across premium web inventory."),
                "Social": ("Targeted Social Media Amplification", "Paid seeding and boosted story placements to drive engagement."),
                "Radio": ("Premium Audio Spot Placement", "High-frequency spot rotation across digital and terrestrial audio."),
                "Print": ("National Press & Editorial Buy", "Full-page placements and contextually relevant advertorials."),
                "Video": ("VOD & YouTube TrueView Ad Spend", "Strategic video sequencing to maximize completion rates."),
                "Events": ("Experiential Promotion & Local Media", "Localized ad support to drive footfall to the physical activation.")
            }

            for channel in media_gaps:
                title, desc = media_map.get(channel, (f"{channel} Media Buy", "Standard media investment."))
                media_items.append({
                    "title": title,
                    "desc": desc,
                    "cost": spend_per_gap,
                    "is_media": True
                })
        
        result['production_items_data'] = prod_data.to_dict('records')
        result['media_items'] = media_items
        result['grand_total'] = production_total + (len(media_items) * (spend_per_gap if media_gaps else 0))
        return result
        
    except Exception as e:
        st.error(f"Logic Error: {e}")
        return None

# --- 3. THE UI ---
def main():
    # ... (Keep Data Loading and Input Cards as they were) ...

    # --- EXECUTION ---
    if st.button("🚀 GENERATE PROPOSAL", type="primary", use_container_width=True):
        if not new_brief_text:
            st.warning("Please provide brief details.")
        else:
            with st.spinner("Optimizing budget across creative and media..."):
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
            
            # 1. Show Production Items
            for item in res['production_items_data']:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**🛠️ {clean_label(item['Component_type'])}**")
                    c1.write(item['Description'])
                    c2.markdown(f"### €{item['Estimated_Budget']:,}")

            # 2. Show the "Maxed Out" Media Gaps
            for m in res['media_items']:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**📢 {m['title']}**")
                    c1.write(m['desc'])
                    c2.markdown(f"### €{m['cost']:,}")
            
            st.divider()
            # Final calculation display
            st.metric("Total Proposal Value", f"€{res['grand_total']:,}", 
                      delta="Budget fully utilized" if res['grand_total'] >= budget_val else f"€{budget_val - res['grand_total']:,} remaining")
        else:
            st.error("AI matched an ID not in the database.")

if __name__ == "__main__":
    main()
