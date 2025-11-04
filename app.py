import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import io
import requests
from datetime import date

# --- Page Configuration ---
st.set_page_config(
    page_title="Brief Matcher Tool",
    page_icon="💡",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- API Key Setup ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Gemini API key not found. Please add your key as a Streamlit Secret.")
    st.stop()

# --- CONSTANTS ---
# ⬇️ PASTE YOUR NEW GOOGLE SHEET URL HERE
BRIEF_LIBRARY_URL = "https://docs.google.com/spreadsheets/d/1_edZXof2yV9D8-luPoodNkfahTyzUE1Dbxg5DU35TSM/edit?usp=sharing"
# We will add the PCA_LIBRARY_URL here later

# --- 1. DATA LOADING FUNCTION ---
@st.cache_data(ttl=600)
def load_briefs(url):
    """Loads and processes the brief library from a Google Sheet URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), header=0)
        df.dropna(how='all', inplace=True)
        df.fillna("", inplace=True)
        # Convert budget columns to numeric, coercing errors to 0
        df['Minimum_Viable_Budget'] = pd.to_numeric(df['Minimum_Viable_Budget'], errors='coerce').fillna(0)
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Error loading data from Google Sheet: {e}")
        st.info("Please ensure your Google Sheet is published to the web and the URL is correct.")
        return []

# --- 2. FORM RESET FUNCTION ---
def reset_form():
    """Resets all the input fields to their default values."""
    st.session_state.new_brief_text = ""
    st.session_state.target_audience = ""
    st.session_state.proposed_channels = []
    st.session_state.start_date = date.today()
    st.session_state.duration_days = 30
    st.session_state.budget_value = 50000
    if 'matches' in st.session_state:
        del st.session_state.matches
    st.rerun()

# --- 3. API & MATCHING LOGIC FUNCTION ---
def find_matches(new_brief, params, user_budget, brief_library):
    """Builds the prompt, calls the AI, and returns the matches."""
    
    # Create a simplified list of briefs for the prompt
    simplified_briefs = []
    for b in brief_library:
        simplified_briefs.append({
            "ID": b.get('ID', ''),
            "Generic_Campaign_Concept": b.get('Generic_Campaign_Concept', ''),
            "Generic_Brand_Category": b.get('Generic_Brand_Category', ''),
            "Generic_Key_Objective": b.get('Generic_Key_Objective', ''),
            "Generic_Audience_Profile": b.get('Generic_Audience_Profile', ''),
            "Core_Creative_Tactic": b.get('Core_Creative_Tactic', ''),
            "Supporting_Media_Tactics": b.get('Supporting_Media_Tactics', ''),
            "Budget_Description": b.get('Budget_Description', ''),
            "Minimum_Viable_Budget": b.get('Minimum_Viable_Budget', 0)
        })

    # --- MODIFIED: This is the new, budget-aware prompt ---
    prompt = f"""
    You are an expert strategic producer. Your task is to find the single best creative idea from a library that matches a new client brief, and then scale that idea to fit the client's budget.

    HERE IS THE NEW BRIEF:
    {new_brief}
    {params}
    Client Budget: €{user_budget}

    HERE IS THE IDEAS LIBRARY:
    {json.dumps(simplified_briefs, indent=2)}

    YOUR TASK:
    1.  Find the *single best* conceptual match from the library based on the brief's objectives and audience.
    2.  Once found, analyze its budget. Compare the 'Client Budget' (€{user_budget}) against the idea's 'Budget_Description' and 'Minimum_Viable_Budget'.
    3.  Follow these rules EXACTLY:

        -   **SCENARIO A:** If the 'Client Budget' is *less than* the matched idea's 'Minimum_Viable_Budget', that idea is unsuitable. REJECT IT and find the next best conceptual match. Repeat this process until you find a match where the client's budget is at least the minimum.
        
        -   **SCENARIO B:** If the 'Client Budget' *meets or exceeds* the 'Minimum_Viable_Budget', it's a good match.
        
    4.  Generate a JSON response for the *one* suitable match you found. The JSON object must contain:
        -   `ID`: The ID of the matched brief.
        -   `scaled_reason`: A client-ready explanation. Start by saying why it's a good conceptual match. Then, explain *how* you scaled it for their €{user_budget} budget.
            -   If the budget fits one of the packages in 'Budget_Description', state that. (e.g., "For your €50,000 budget, we can execute the 'Full' €46,200 package...").
            -   If the budget is between packages, recommend the lower package (e.g., "Your €30,000 budget is a perfect fit for the 'Reduced' €23,600 package...").
            -   If the budget is above the minimum but below the full package, recommend the core tactic (e.g., "For your €120,000 budget, we recommend focusing on the powerful 'Core_Creative_Tactic'...").
    
    IMPORTANT: Write the 'scaled_reason' in a natural, persuasive tone. Do not mention field names like 'Minimum_Viable_Budget' or 'Generic_Brand_Category'. Just state the facts.

    If there are no good matches that fit the budget rules, return an empty array [].
    Return only a single JSON object in an array: [{{ "ID": "...", "scaled_reason": "..." }}]
    """
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash", 
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(prompt)
        matches = json.loads(response.text)
        return matches
    except Exception as e:
        st.error(f"An error occurred with the API: {e}")
        st.warning("Could not connect to the API. Please check your API key and try again.")
        return []

# --- 4. RESULTS DISPLAY FUNCTION ---
def display_matches(matches, brief_library):
    """Renders the matching briefs in Streamlit expanders."""
    
    st.subheader("💡 Top Creative Idea") # Changed title
    
    if matches:
        match = matches[0] # We only expect one match now
        match_id = match.get('ID')
        reason = match.get('scaled_reason', 'No reason provided.') # Use the new 'scaled_reason'
        
        if not match_id:
            st.warning("A match was found but it was missing an ID.")
            return

        original_brief = next((b for b in brief_library if str(b.get('ID')) == str(match_id)), None)
        
        if original_brief:
            expander_title = original_brief.get('Generic_Campaign_Concept', 'No Title')
            with st.expander(f"**{expander_title}**", expanded=True): # Expanded by default
                
                st.markdown(f"**Budget-Aware Recommendation:**")
                st.info(reason) # Display the new scaled reason in an info box
                
                st.markdown("---")
                st.markdown(
                    f"""
                    **Brand Category:** {original_brief.get('Generic_Brand_Category', 'N/A')}  
                    **Audience Profile:** {original_brief.get('Generic_Audience_Profile', 'N/A')}  
                    **Key Objective:** {original_brief.get('Generic_Key_Objective', 'N/A')}  
                    **Core Tactic:** {original_brief.get('Core_Creative_Tactic', 'N/A')}  
                    **Supporting Tactics:** {original_brief.get('Supporting_Media_Tactics', 'N/A')}  
                    **Original Budget Options:** {original_brief.get('Budget_Description', 'N/A')}
                    """
                )
        else:
            st.error(f"Matched brief ID '{match_id}' not found in the library.")
    else: 
        st.info("No close matches found that fit the budget requirements. This is a great opportunity for a brand new idea!")

# --- 5. MAIN APPLICATION ---
def main():
    """Runs the main Streamlit application."""
    
    st.title("💡 Brief Matcher Tool")
    st.markdown("---")
    
    # Load the data
    brief_library = load_briefs(BRIEF_LIBRARY_URL)

    st.subheader("Match a New Brief")
    st.write("Paste the new client brief details and select key parameters to find the most relevant past ideas.")

    # --- Input Form ---
    new_brief_text = st.text_area(
        "New Brief Details:",
        height=150,
        placeholder="e.g., 'We need to drive app downloads for our new budgeting app aimed at young professionals. Focus on simplicity and automation.'",
        key="new_brief_text"
    )
    col1, col2 = st.columns(2)
    with col1:
        target_audience = st.text_input(
            "Target Audience:",
            placeholder="e.g., Gen Z, young professionals",
            key="target_audience"
        )
    with col2:
        proposed_channels = st.multiselect(
            "Proposed Media Channels:",
            options=[
                'Print', 'Radio', 'Video', 'Digital Display', 'Digital Audio', 'Events', 'Social Media'
            ],
            key="proposed_channels"
        )
    col3, col4 = st.columns(2)
    with col3:
        start_date = st.date_input("Start Date:", date.today(), key="start_date")
    with col4:
        duration_days = st.number_input(
            "Duration (days):", min_value=1, max_value=365, value=30, key="duration_days"
        )
    
    # MODIFIED: Increased max budget range
    budget_value = st.slider(
        "Budget (in €):",
        min_value=1000,
        max_value=300000, 
        value=50000,
        step=1000,
        key="budget_value",
        help="Move the slider to set rough budget."
    )
    
    budget_k = st.session_state.budget_value / 1000
    budget_label = f"€{int(budget_k)}k"
    if st.session_state.budget_value == 300000:
        budget_label = "€300k+"

    # --- Buttons ---
    find_col, reset_col = st.columns(2)
    with find_col:
        if st.button("Find Matches", use_container_width=True, type="primary"):
            if not st.session_state.new_brief_text.strip():
                st.warning("Please paste a brief to match.")
            elif not brief_library:
                st.warning("Brief repository is empty or could not be loaded.")
            else:
                with st.spinner("Finding the best matches..."):
                    additional_params = f"""
                    Target Audience: {st.session_state.target_audience}
                    Proposed Media Channels: {', '.join(st.session_state.proposed_channels)}
                    Duration: {st.session_state.duration_days} days
                    """
                    
                    # Call the matching function
                    matches = find_matches(
                        st.session_state.new_brief_text,
                        additional_params,
                        st.session_state.budget_value, # MODIFIED: Pass the raw number
                        brief_library
                    )
                    st.session_state.matches = matches

    with reset_col:
        st.button("Reset Fields", on_click=reset_form, use_container_width=True)

    # --- Display Results ---
    st.markdown("---")
    if 'matches' in st.session_state:
        # Call the display function
        display_matches(st.session_state.matches, brief_library)

# --- Run the app ---
if __name__ == "__main__":
    main()
