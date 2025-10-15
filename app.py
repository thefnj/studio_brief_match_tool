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
        # MODIFIED: Ensure first row is treated as header
        df = pd.read_csv(io.StringIO(response.text), header=0)
        df.dropna(how='all', inplace=True)
        # MODIFIED: Fill any potential empty values with empty strings
        df.fillna("", inplace=True)
        briefs = df.to_dict('records')
        return briefs
    except requests.exceptions.RequestException as e:
        st.error(f"Error loading data from Google Sheet: {e}")
        return []
    except Exception as e:
        st.error(f"An error occurred processing the Google Sheet data: {e}")
        st.info("Please ensure your Google Sheet is published to the web and the URL is correct.")
        return []


brief_library = load_briefs()

# --- Function to reset the session state ---
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

# --- Main Application Logic ---
st.title("💡 Brief Matcher Tool")
st.markdown("---")

st.subheader("Match a New Brief")
st.write("Paste the new client brief details and select key parameters to find the most relevant past ideas and case studies.")

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
        "Duration (days):",
        min_value=1,
        max_value=365,
        value=30,
        key="duration_days"
    )

budget_value = st.slider(
    "Budget (in €):",
    min_value=1000,
    max_value=250000, # Increased max budget
    value=50000,
    step=1000,
    key="budget_value",
    help="Move the slider to set rough budget."
)

budget_k = st.session_state.budget_value / 1000
budget_label = f"€{int(budget_k)}k"
if st.session_state.budget_value >= 1000000:
    budget_label = f"€{st.session_state.budget_value / 1000000:.1f}M"
elif st.session_state.budget_value == 250000:
    budget_label = "€250k+"

# --- Columns for buttons ---
find_col, reset_col = st.columns(2)

with find_col:
    if st.button("Find Matches", use_container_width=True, type="primary"):
        if not st.session_state.new_brief_text.strip():
            st.warning("Please paste a brief to match.")
        elif not brief_library:
            st.warning("Brief repository is empty or could not be loaded. Please check your Google Sheet and URL.")
        else:
            with st.spinner("Finding the best matches..."):
                additional_params = f"""
                Target Audience: {st.session_state.target_audience}
                Proposed Media Channels: {', '.join(st.session_state.proposed_channels)}
                Budget: {budget_label}
                Duration: {st.session_state.duration_days} days starting {st.session_state.start_date}
                """
                
                simplified_briefs = []
                for b in brief_library:
                    # MODIFIED: Ensure we're using the new column name
                    concept = b.get('Generic_Campaign_Concept') or b.get('Campaign Title', '')
                    
                    brief_data = {
                        "ID": b.get('ID', ''),
                        "Campaign_Type": b.get('Campaign_Type', 'Idea'),
                        "Generic_Brand_Category": b.get('Generic_Brand_Category', ''),
                        "Generic_Campaign_Concept": concept,
                        "Generic_Audience_Profile": b.get('Generic_Audience_Profile', ''),
                        "Generic_Key_Objective": b.get('Generic_Key_Objective', ''),
                        "Generic_Media_Strategy": b.get('Generic_Media_Strategy', '')
                    }
                    if brief_data["Campaign_Type"] == 'Case Study' and b.get('Key_Results_Summary'):
                        brief_data["Key_Results_Summary"] = b.get('Key_Results_Summary')
                    
                    simplified_briefs.append(brief_data)

                # <-- MODIFIED: A much clearer prompt on HOW to write the reason
                prompt = f"""
                You are an expert creative strategist. Your task is to find the 3 most relevant past campaigns from a library, given a new client brief.
                The library contains two types of campaigns: 'Idea' and 'Case Study'.
                - 'Idea': A creative concept. Match this based on conceptual similarity.
                - 'Case Study': A campaign with proven results. If a Case Study is a strong match, your reasoning must highlight how its proven success is relevant to the new brief.

                New Brief Details: "{st.session_state.new_brief_text}"
                {additional_params}
                
                Past Campaigns Library:
                {json.dumps(simplified_briefs, indent=2)}
                
                You must provide a JSON array of the top 3 matches. Each object in the array MUST contain two keys: 'ID' and 'reason'. 
                It is critical that the 'ID' field is included and is not empty.
                
                IMPORTANT: Write the 'reason' in a natural, persuasive tone, as if you were explaining it to a client. 
                DO NOT mention the internal field names like 'Generic_Brand_Category' or 'Generic_Audience_Profile' in your reasoning. 
                Instead, just state the facts (e.g., "This concept is a great fit because it targets an affluent, adventurous audience, similar to your target...").

                If there are no good matches, return an empty array.
                """
                
                try:
                    model = genai.GenerativeModel(
                        model_name="gemini-2.5-flash", 
                        generation_config={"response_mime_type": "application/json"}
                    )
                    response = model.generate_content(prompt)
                    
                    matches_json = response.text
                    st.session_state.matches = json.loads(matches_json)

                except Exception as e:
                    st.error(f"An error occurred with the API: {e}")
                    st.warning("Could not connect to the API. Please check your API key and try again.")

with reset_col:
    st.button("Reset Fields", on_click=reset_form, use_container_width=True)

# --- Decoupled display logic ---
if 'matches' in st.session_state:
    matches = st.session_state.matches
    if matches:
        st.success("Found some great matches!")
        st.subheader("Top Matches")
        for match in matches:
            match_id = match.get('ID')
            reason = match.get('reason', 'No reason provided.')
            
            if not match_id:
                st.warning("A match was found but it was missing an ID.")
                continue

            original_brief = next((b for b in brief_library if str(b.get('ID')) == str(match_id)), None)
            
            if original_brief:
                # <-- MODIFIED: Use the generic concept for the title
                expander_title = original_brief.get('Generic_Campaign_Concept') or original_brief.get('Campaign Title', 'No Title')
                with st.expander(f"**{expander_title}**"):
                    
                    campaign_type = original_brief.get('Campaign_Type', 'Idea')
                    if campaign_type == 'Case Study':
                        st.info("🚀 **Case Study: Proven Success**")
                    
                    st.markdown(f"**Match Reason:** {reason}")
                    
                    if campaign_type == 'Case Study' and original_brief.get('Key_Results_Summary'):
                        st.markdown("---")
                        # <-- MODIFIED: Use markdown for better formatting of results
                        st.markdown("**Key Results from this Campaign:**")
                        st.markdown(original_brief.get('Key_Results_Summary'))
                    
                    st.markdown("---")

                    # <-- MODIFIED: Display the GENERIC details instead of the original ones
                    st.markdown(
                        f"""
                        **Brand Category:** {original_brief.get('Generic_Brand_Category', 'N/A')}  
                        **Audience Profile:** {original_brief.get('Generic_Audience_Profile', 'N/A')}  
                        **Key Objective:** {original_brief.get('Generic_Key_Objective', 'N/A')}  
                        **Media Strategy:** {original_brief.get('Generic_Media_Strategy', 'N/A')}  
                        **Original Budget:** {original_brief.get('Budget', 'N/A')}  
                        **Original Duration:** {original_brief.get('Duration', 'N/A')}
                        """
                    )
            else:
                st.error(f"Matched brief ID '{match_id}' not found in the library.")
    else: 
        st.info("No close matches found. This is a great opportunity for a brand new idea!")

st.markdown("---")
