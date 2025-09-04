import streamlit as st
import google.generativeai as genai
import json
import pandas as pd # <-- Add this import
import io # <-- Add this import
import requests # <-- Add this import
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
# Replace with your Google Sheet URL (the CSV export URL)
# Ensure your sheet headers are: ID, Original Brand, Campaign Title, Target Audience, Key Objective, Core Message, Proposed Media Channels, Budget, Duration, Brand Suitability
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

# --- Main Application Logic ---
st.title("💡 Brief Matcher Tool")
st.markdown("---")

st.subheader("Match a New Brief")
st.write("Paste the new client brief details and select key parameters to find the most relevant past ideas.")

new_brief_text = st.text_area(
    "New Brief Details:",
    height=150,
    placeholder="e.g., 'We need to drive app downloads for our new budgeting app aimed at young professionals. Focus on simplicity and automation.'"
)

# New input fields for filtering
col1, col2 = st.columns(2)
with col1:
    target_audience = st.text_input(
        "Target Audience:",
        placeholder="e.g., Gen Z, young professionals"
    )
with col2:
    proposed_channels = st.multiselect(
        "Proposed Media Channels:",
        options=[
            'Print', 'Radio', 'Video', 'Digital Display', 'Digital Audio'
        ]
    )

col3, col4 = st.columns(2)
with col3:
    start_date = st.date_input("Start Date:", date.today())
with col4:
    duration_days = st.number_input(
        "Duration (days):",
        min_value=1,
        max_value=365,
        value=30
    )

budget_value = st.slider(
    "Budget (in €):",
    min_value=1000,
    max_value=100000,
    value=500,
    step=1,
    help="Move the slider to set a budget. Values are in thousands (e.g., 100 means €100k)."
)
budget_label = f"€{budget_value}k"
if budget_value == 1000:
    budget_label = "€1M+"

if st.button("Find Matches", use_container_width=True, type="primary"):
    if not new_brief_text.strip():
        st.warning("Please paste a brief to match.")
    elif not brief_library:
        st.warning("Brief repository is empty. Please check your Google Sheet and URL.")
    else:
        with st.spinner("Finding the best matches..."):
            # Construct a more detailed prompt for the AI
            additional_params = f"""
            Target Audience: {target_audience}
            Proposed Media Channels: {', '.join(proposed_channels)}
            Budget: {budget_label}
            Duration: {duration_days} days starting {start_date}
            """
            
            past_briefs_text = "\n\n".join([
                f"""
                ID: {b.get('ID', '')}
                Original Brand: {b.get('Original Brand', '')}
                Campaign Title: {b.get('Campaign Title', '')}
                Target Audience: {b.get('Target Audience', '')}
                Key Objective: {b.get('Key Objective', '')}
                Core Message: {b.get('Core Message', '')}
                Proposed Media Channels: {b.get('Proposed Media Channels', '')}
                Budget: {b.get('Budget', '')}
                Duration: {b.get('Duration', '')}
                Brand Suitability: {b.get('Brand Suitability', '')}
                """
                for b in brief_library
            ])

            prompt = f"""
            You are a creative strategist. Given a new client brief with specific parameters, find the 3 most relevant briefs from a list of past ideas.
            
            New Brief Details: "{new_brief_text}"
            {additional_params}
            
            Past Briefs:
            {past_briefs_text}
            
            Based on the new brief and the past briefs, provide a JSON array of the top 3 matches. Each object in the array must contain the 'ID' of the past brief and a 'reason' for the match. If there are no good matches, return an empty array.
            """
            
            try:
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash-preview-05-20",
                    generation_config={"response_mime_type": "application/json"}
                )
                response = model.generate_content(prompt)
                
                matches_json = response.text
                matches = json.loads(matches_json)

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
                                    
                                    **Original Brand:** {original_brief.get('Original Brand', 'N/A')}
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
                else:
                    st.info("No close matches found. Time for a new idea!")
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.warning("Could not connect to the API. Please check your API key and try again.")

st.markdown("---")

st.subheader(f"💡 Existing Brief Repository ({len(brief_library)} briefs)")
st.write("This is your full repository of past briefs.")

for brief in brief_library:
    with st.expander(f"**{brief.get('Campaign Title', 'No Title')}**"):
        st.markdown(
            f"""
            **Original Brand:** {brief.get('Original Brand', 'N/A')}
            **Target Audience:** {brief.get('Target Audience', 'N/A')}
            **Key Objective:** {brief.get('Key Objective', 'N/A')}
            **Core Message:** {brief.get('Core Message', 'N/A')}
            **Proposed Media Channels:** {brief.get('Proposed Media Channels', 'N/A')}
            **Budget:** {brief.get('Budget', 'N/A')}
            **Duration:** {brief.get('Duration', 'N/A')}
            """
        )




