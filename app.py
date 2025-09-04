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
