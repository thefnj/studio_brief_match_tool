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

# --- Load Brief Library from Google Sheet ---
google_sheet_url = "https://docs.google.com/spreadsheets/d/1_edZXof2yV9D8-luPoodNkfahTyzUE1Dbxg5DU35TSM/gviz/tq?tqx=out:csv&sheet=Sheet1"

@st.cache_data(ttl=600)
def load_briefs():
    try:
        response = requests.get(google_sheet_url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df.dropna(how='all', inplace=True)
        briefs = df.to_dict('records')
        return briefs
    except requests.exceptions.RequestException as e:
        st.error(f"Error loading data from Google Sheet: {e}")
        return []

brief_library = load_briefs()

# --- NEW: Function to reset the session state ---
def reset_form():
    """Resets all the input fields to their default values."""
    st.session_state.new_brief_text = ""
    st.session_state.target_audience = ""
    st.session_state.proposed_channels = []
    st.session_state.start_date = date.today()
    st.session_state.duration_days = 30
    st.session_state.budget_value = 50000 # Corrected default to match slider
    # Clear previous matches if they exist
    if 'matches' in st.session_state:
        del st.session_state.matches
    st.rerun()

# --- Main Application Logic ---
st.title("💡 Brief Matcher Tool")
st.markdown("---")

st.subheader("Match a New Brief")
st.write("Paste the new client brief details and select key parameters to find the most relevant past ideas.")

# MODIFIED: Added 'key' to each widget
new_brief_text = st.text_area(
    "New Brief Details:",
    height=150,
    placeholder="e.g., 'We need to drive app downloads for our new budgeting app aimed at young professionals. Focus on simplicity and automation.'",
    key="new_brief_text" # <-- MODIFIED
)

col1, col2 = st.columns(2)
with col1:
    target_audience = st.text_input(
        "Target Audience:",
        placeholder="e.g., Gen Z, young professionals",
        key="target_audience" # <-- MODIFIED
    )
with col2:
    proposed_channels = st.multiselect(
        "Proposed Media Channels:",
        options=[
            'Print', 'Radio', 'Video', 'Digital Display', 'Digital Audio'
        ],
        key="proposed_channels" # <-- MODIFIED
    )

col3, col4 = st.columns(2)
with col3:
    start_date = st.date_input("Start Date:", date.today(), key="start_date") # <-- MODIFIED
with col4:
    duration_days = st.number_input(
        "Duration (days):",
        min_value=1,
        max_value=365,
        value=30,
        key="duration_days" # <-- MODIFIED
    )

budget_value = st.slider(
    "Budget (in €):",
    min_value=1000,
    max_value=100000,
    value=50000, # <-- Corrected default value to be in the middle
    step=1000,    # <-- Changed step for better usability
    key="budget_value", # <-- MODIFIED
    help="Move the slider to set rough budget."
)

# Use session_state value for logic
budget_k = st.session_state.budget_value / 1000
budget_label = f"€{int(budget_k)}k"
if st.session_state.budget_value == 100000:
    budget_label = "€100k+"

# --- NEW: Columns for buttons ---
find_col, reset_col = st.columns(2)

with find_col:
    if st.button("Find Matches", use_container_width=True, type="primary"):
        # MODIFIED: Check session state for input
        if not st.session_state.new_brief_text.strip():
            st.warning("Please paste a brief to match.")
        elif not brief_library:
            st.warning("Brief repository is empty. Please check your Google Sheet and URL.")
        else:
            with st.spinner("Finding the best matches..."):
                # Construct a more detailed prompt for the AI
                # MODIFIED: Read all values from st.session_state
                additional_params = f"""
                Target Audience: {st.session_state.target_audience}
                Proposed Media Channels: {', '.join(st.session_state.proposed_channels)}
                Budget: {budget_label}
                Duration: {st.session_state.duration_days} days starting {st.session_state.start_date}
                """
                
                # Create a simplified list of briefs for the prompt
                simplified_briefs = []
                for b in brief_library:
                    simplified_briefs.append({
                        "ID": b.get('ID', ''),
                        "Campaign Title": b.get('Campaign Title', ''),
                        "Target Audience": b.get('Target Audience', ''),
                        "Key Objective": b.get('Key Objective', ''),
                        "Core Message": b.get('Core Message', ''),
                        "Proposed Media Channels": b.get('Proposed Media Channels', ''),
                        "Budget": b.get('Budget', ''),
                        "Duration": b.get('Duration', '')
                    })

                prompt = f"""
                You are a creative strategist. Given a new client brief with specific parameters, find the 3 most relevant briefs from a list of past ideas.
                
                New Brief Details: "{st.session_state.new_brief_text}"
                {additional_params}
                
                Past Briefs:
                {json.dumps(simplified_briefs, indent=2)}
                
                Based on the new brief and the past briefs, provide a JSON array of the top 3 matches. Each object in the array must contain the 'ID' of the past brief and a 'reason' for the match. If there are no good matches, return an empty array.
                """
                
                try:
                    model = genai.GenerativeModel(
                        model_name="gemini-1.5-flash", # Updated to a common model name
                        generation_config={"response_mime_type": "application/json"}
                    )
                    response = model.generate_content(prompt)
                    
                    matches_json = response.text
                    # NEW: Store matches in session state to persist them
                    st.session_state.matches = json.loads(matches_json)

                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    st.warning("Could not connect to the API. Please check your API key and try again.")

with reset_col:
    # --- NEW: Reset Button ---
    st.button("Reset Fields", on_click=reset_form, use_container_width=True)


# --- NEW: Decoupled display logic ---
# This part now reads from session_state and displays results.
# It runs independently of the button clicks.
if 'matches' in st.session_state:
    matches = st.session_state.matches
    if matches:
        st.success("Found some great matches!")
        st.subheader("Top Matches")
        for match in matches:
            match_id = match['ID']
            reason = match['reason']
            
            original_brief = next((b for b in brief_library if str(b.get('ID')) == str(match_id)), None)
            
            if original_brief:
                with st.expander(f"**{original_brief.get('Campaign Title', 'No Title')}**"):
                    st.markdown(
                        f"""
                        **Match Reason:** {reason}
                        
                        **Target Audience:** {original_brief.get('Target Audience', 'N/A')}
                        **Key Objective:** {original_brief.get('Key Objective', 'N/A')}
                        **Core Message:** {original_brief.get('Core Message', 'N/A')}
                        **Proposed Media Channels:** {original_brief.get('Proposed Media Channels', 'N/A')}
                        **Budget:** {original_brief.get('Budget', 'N/A')}
                        **Duration:** {original_brief.get('Duration', 'N/A')}
                        """
                    )
            else:
                st.error(f"Matched brief ID '{match_id}' not found in the library.")
    else: # This handles the case where the API returns an empty list []
        st.info("No close matches found. Time for a new idea!")


st.markdown("---")
