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
# Replace with your Google Sheet URL
google_sheet_url = "https://docs.google.com/spreadsheets/d/1_edZXof2yV9D8-luPoodNkfahTyzUE1Dbxg5DU35TSM/gviz/tq?tqx=out:csv&sheet=Sheet1"

@st.cache_data(ttl=600)  # Cache data for 10 minutes to avoid hitting API too often
def load_briefs():
    try:
        response = requests.get(google_sheet_url)
        response.raise_for_status() # Raise an exception for bad status codes
        df = pd.read_csv(io.StringIO(response.text))
        # Assuming your sheet has 'title' and 'summary' columns
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

# Text area for user input
new_brief = st.text_area(
    "New Brief Details:",
    height=150,
    placeholder="e.g., 'We need to drive app downloads for our new budgeting app aimed at young professionals. Focus on simplicity and automation.'"
)

# Button to trigger matching
if st.button("Find Matches", use_container_width=True, type="primary"):
    if not new_brief.strip():
        st.warning("Please paste a brief to match.")
    elif not brief_library:
        st.warning("Brief library is empty. Please check your Google Sheet and URL.")
    else:
        with st.spinner("Finding the best matches..."):
            # Construct the prompt for the Gemini API
            prompt = f"""
            You are a creative strategist. Given a new client brief, find the 3 most relevant briefs from a list of past ideas.

            New Brief: "{new_brief}"

            Past Briefs:
            {json.dumps(brief_library, indent=2)}

            Based on the new brief and the past briefs, provide a JSON array of the top 3 matches. Each object in the array should contain the 'id' of the past brief and a 'reason' for the match. If there are no good matches, return an empty array.
            """

            try:
                # Call the Gemini API
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash-preview-05-20",
                    generation_config={"response_mime_type": "application/json"}
                )
                response = model.generate_content(prompt)

                # Parse the JSON response
                matches_json = response.text
                matches = json.loads(matches_json)

                if matches:
                    st.success("Found some great matches!")
                    st.subheader("Top Matches")
                    for match in matches:
                        match_id = match['id']
                        reason = match['reason']

                        # Find the original brief from the hardcoded library
                        original_brief = next((b for b in brief_library if b.get('id') == match_id), None)

                        if original_brief:
                            st.markdown(f"**{original_brief.get('title', 'No Title')}**")
                            st.write(f"**Reason for match:** {reason}")
                            st.write(original_brief.get('summary', 'No Summary'))
                            st.markdown("---")
                        else:
                            st.error(f"Matched brief ID '{match_id}' not found in the library.")
                else:
                    st.info("No close matches found. Time for a new idea!")
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.warning("Could not connect to the API. Please check your API key and try again.")

st.markdown("---")

st.subheader(f"💡 Existing Brief Library ({len(brief_library)} briefs)")
st.write("This is your repository of past briefs that can be used for new campaigns.")

for brief in brief_library:
    st.expander(f"**{brief.get('title', 'No Title')}**").write(brief.get('summary', 'No Summary'))
