import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
from datetime import date

# ... (Page Config and API Setup remain the same) ...

# --- 1. DATA LOADING FUNCTION ---
@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # 1. Use 'keep_default_na=False' to prevent Pandas from guessing types too early
        df = pd.read_csv(io.StringIO(response.text), keep_default_na=False)
        
        # 2. Clean Budget Columns (Common culprit for this error)
        # We look for columns with 'Budget' or 'Cost' in the name
        for col in df.columns:
            if 'Budget' in col or 'Cost' in col:
                # Remove currency symbols, commas, and whitespace
                df[col] = df[col].astype(str).str.replace(r'[€, ]', '', regex=True)
                # Convert to numeric, turning errors (like blanks) into 0
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# --- 2. API & MATCHING LOGIC ---
def find_matches(new_brief, params, user_budget, ideas_df, components_df):
    # Prepare the data for Gemini
    # We only send relevant columns to save tokens
    ideas_list = ideas_df[['Idea_ID', 'Generic_idea_title', 'Summary', 'Budget_band']].to_dict('records')
    
    # We send ALL components, or we could filter them in the prompt logic
    components_list = components_df[['Component_ID', 'Parent_Idea_ID', 'Component_type', 'Description', 'Estimated_Budget']].to_dict('records')

    prompt = f"""
    You are a Strategic Producer. 
    TASK: 
    1. Match the client brief to the best CONCEPT from the Ideas Library.
    2. From that specific Idea, select a combination of COMPONENTS that fit within the Client Budget.
    
    CLIENT BRIEF: {new_brief}
    TARGET BUDGET: €{user_budget}
    
    IDEAS LIBRARY:
    {json.dumps(ideas_list)}
    
    COMPONENTS LIBRARY (linked by Parent_Idea_ID):
    {json.dumps(components_list)}
    
    RULES:
    - Only select components that belong to the matched Idea.
    - The sum of 'Estimated_Budget' for selected components MUST NOT exceed €{user_budget}.
    - Priority: Include 'Core' or 'High Impact' components first.
    
    RETURN JSON ONLY:
    {{
        "matched_idea_id": "IDEA-001",
        "reasoning": "...",
        "selected_component_ids": ["COMP-001", "COMP-002"],
        "total_estimated_cost": 45000
    }}
    """

    model = genai.GenerativeModel("gemini-1.5-flash") # Using 1.5 for faster hackathon response
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return json.loads(response.text)

# --- 3. DISPLAY RESULTS ---
def display_results(match_data, ideas_df, components_df):
    idea = ideas_df[ideas_df['Idea_ID'] == match_data['matched_idea_id']].iloc[0]
    
    st.subheader(f"💡 Recommended Idea: {idea['Generic_idea_title']}")
    st.info(match_data['reasoning'])
    
    st.write("### 🛠️ Custom Component Build-out")
    st.write(f"**Total Estimated Budget:** €{match_data['total_estimated_cost']:,}")
    
    # Display only the selected components
    selected_comps = components_df[components_df['Component_ID'].isin(match_data['selected_component_ids'])]
    
    for _, row in selected_comps.iterrows():
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"**{row['Component_type']}**")
            col1.write(row['Description'])
            col2.write(f"€{row['Estimated_Budget']}")

# --- MAIN APP ---
def main():
    st.title("Brief Matcher Tool 2.0")
    
    # Load both
    ideas_df = load_data("https://docs.google.com/spreadsheets/d/1_edZXof2yV9D8-luPoodNkfahTyzUE1Dbxg5DU35TSM/edit?gid=1655639181#gid=1655639181")
    components_df = load_data("https://docs.google.com/spreadsheets/d/1_edZXof2yV9D8-luPoodNkfahTyzUE1Dbxg5DU35TSM/edit?gid=571399293#gid=571399293")
    
    # ... (Inputs for Brief, Audience, and Budget Slider) ...
    
    if st.button("Find Matches"):
        with st.spinner("Analyzing libraries..."):
            match_data = find_matches(new_brief_text, "", budget_value, ideas_df, components_df)
            st.session_state.match_data = match_data

    if 'match_data' in st.session_state:
        display_results(st.session_state.match_data, ideas_df, components_df)

if __name__ == "__main__":
    main()
