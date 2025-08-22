import streamlit as st
import google.generativeai as genai
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="Brief Matcher Tool",
    page_icon="💡",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- API Key Setup ---
# Your Gemini API key should be stored as a Streamlit Secret.
# In your Streamlit Cloud app dashboard, go to "Secrets" and add
# an entry like this:
# GEMINI_API_KEY="YOUR_API_KEY_HERE"
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Gemini API key not found. Please add your key as a Streamlit Secret.")
    st.stop()

# --- Sample Brief Library ---
# This is a sample list of briefs. You can replace this with data from a CSV or Google Sheet.
brief_library = [
    {
        "id": "brief-1",
        "title": "Eco-Friendly Campaign for Young Adults",
        "summary": "Campaign to promote a new line of reusable coffee cups to a Gen Z audience on social media. The focus is on sustainability, lifestyle, and vibrant, shareable content. Channels: Instagram, TikTok, and YouTube Shorts."
    },
    {
        "id": "brief-2",
        "title": "Financial Literacy for New Grads",
        "summary": "A series of digital ads and blog posts targeting recent college graduates to introduce them to a new mobile banking app. The core message is 'make smart money moves.' Channels: Financial news websites, educational blogs, and LinkedIn."
    },
    {
        "id": "brief-3",
        "title": "B2B Software Launch",
        "summary": "A campaign to generate leads for a new project management software. Target audience: small business owners and enterprise managers. The campaign will feature a series of case studies and webinars. Channels: Google Ads, industry-specific forums, and email marketing."
    },
    {
        "id": "brief-4",
        "title": "Summer Music Festival Promotion",
        "summary": "A campaign to drive ticket sales for a summer music festival in a major city. Target audience: music lovers aged 18-35. The campaign will focus on FOMO and unique experiences. Channels: Spotify, local radio, and social media event pages."
    },
    {
        "id": "brief-5",
        "title": "Healthy Pet Food Product Launch",
        "summary": "Launch a new line of organic, grain-free dog food. Target audience: millennial pet owners. The campaign will highlight product benefits like 'better digestion' and 'healthy coat.' Channels: Pet owner blogs, Instagram, and influencer collaborations."
    },
    {
        "id": "brief-6",
        "title": "Luxury Travel Agency Branding",
        "summary": "Rebranding campaign for a high-end travel agency. The goal is to position the brand as a provider of 'once-in-a-lifetime' experiences. Target audience: affluent individuals and couples aged 40+. Channels: Travel magazines, high-end lifestyle blogs, and targeted digital display ads."
    }
]

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
                        original_brief = next((b for b in brief_library if b['id'] == match_id), None)
                        
                        if original_brief:
                            st.markdown(f"**{original_brief['title']}**")
                            st.write(f"**Reason for match:** {reason}")
                            st.write(original_brief['summary'])
                            st.markdown("---")
                        else:
                            st.error(f"Matched brief ID '{match_id}' not found in the library.")
                else:
                    st.info("No close matches found. Time for a new idea!")
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.warning("Could not connect to the API. Please check your API key and try again.")

st.markdown("---")

st.subheader("💡 Existing Brief Library")
st.write("This is your repository of past briefs that can be used for new campaigns.")

for brief in brief_library:
    st.expander(f"**{brief['title']}**").write(brief['summary'])
