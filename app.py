import streamlit as st
import google.generativeai as genai
import json
import pandas as pd # <-- Add this import
import io # <-- Add this import
import requests # <-- Add this import

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
google_sheet_url = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/gviz/tq?tqx=out:csv&sheet=Sheet1"

@st.cache_data(ttl=600)  # Cache data for 10 minutes
def load_briefs():
    try:
        response = requests.get(google_sheet_url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        # Remove any rows with all empty values that might be at the bottom
        df.dropna(how='all', inplace=True)
        # Convert DataFrame to a list of dictionaries
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
st.write("Paste the new client brief details below to find the most relevant past ideas.")

new_brief = st.text_area(
    "New Brief Details:",
    height=150,
    placeholder="e.g., 'We need to drive app downloads for our new budgeting app aimed at young professionals. Focus on simplicity and automation.'"
)

if st.button("Find Matches", use_container_width=True, type="primary"):
    if not new_brief.strip():
        st.warning("Please paste a brief to match.")
    elif not brief_library:
        st.warning("Brief repository is empty. Please check your Google Sheet and URL.")
    else:
        with st.spinner("Finding the best matches..."):
            # Construct the prompt using all the fields from the sheet for better context
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
            You are a creative strategist. Given a new client brief, find the 3 most relevant briefs from a list of past ideas.
            
            New Brief: "{new_brief}"
            
            Past Briefs:
            {past_briefs_text}
            
            Based on the new brief and the past briefs, provide a JSON array of the top 3 matches. Each object in the array should contain the 'ID' of the past brief and a 'reason' for the match. If there are no good matches, return an empty array.
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
                            st.expander(f"**{original_brief.get('Campaign Title', 'No Title')}**").markdown(
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
    st.expander(f"**{brief.get('Campaign Title', 'No Title')}**").markdown(
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



