import streamlit as st
import os
import psycopg
import time
from google import genai
from google.genai import types
from PIL import Image

# 1. Page Configuration
st.set_page_config(page_title="Bay Area Housing Assistant", page_icon="🏠", layout="centered")

st.title("🏠 Bay Area Housing Stability Assistant")
st.write("Get accurate educational guidance, legal timelines, and local resources for your housing issues.")
st.markdown("---")

# 2. Grab Secrets Securely
DATABASE_URL = st.secrets.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not DATABASE_URL or not GEMINI_API_KEY:
    st.error("❌ Missing configuration secrets. Please add DATABASE_URL and GEMINI_API_KEY to your Streamlit App Secrets.")
    st.stop()

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# 3. Create Inputs on the UI
issue_title = st.text_input("Issue Title", placeholder="e.g., Received 3-Day Notice over utility dispute in Oakland")
issue_body = st.text_area("Describe your situation in detail", placeholder="Paste the text of your notice or explain what happened here...", height=150)

# Picture upload feature
uploaded_file = st.file_uploader("Upload a photo of your official notice or housing issue (Optional)", type=["png", "jpg", "jpeg"])

image_object = None
if uploaded_file:
    image_object = Image.open(uploaded_file)
    st.image(image_object, caption="📷 Document Preview", use_container_width=True)

st.markdown("---")

# 4. Define the AI Generation Process inside a clean function
def run_housing_ai():
    with st.spinner("🧠 Gemini is analyzing your case and generating custom resources..."):
        try:
            # Resilient Database Connection with Retry Loop for Neon Cold Starts
            conn = None
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    # Added connect_timeout=15 to give the serverless database breathing room to wake up
                    conn = psycopg.connect(DATABASE_URL, connect_timeout=15)
                    break 
                except (psycopg.OperationalError, psycopg.Error) as db_err:
                    if attempt < max_retries - 1:
                        # Wait 3 seconds before trying again to allow the DB to finish booting up
                        time.sleep(3)
                        continue
                    else:
                        raise db_err

            # Once connection is established, execute queries safely
            with conn:
                with conn.cursor() as cur:
                    # Keep database schema secure
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS chat_sessions (
                            session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            metadata JSONB
                        );
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS chat_messages (
                            message_id SERIAL PRIMARY KEY,
                            session_id UUID REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                            role VARCHAR(20) NOT NULL,
                            content TEXT NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()

                    system_instruction = (
                        "You are the Bay Area Housing Stability Assistant, an expert AI legal information companion specializing in tenant rights in the San Francisco Bay Area.\n\n"
                        "Your primary mission is to provide an accurate, clear, and actionable solution to the tenant's crisis. Structure your response as follows:\n\n"
                        "1. CRITICAL ASSESSMENT & SOLUTION: Analyze the specific crisis, timelines, and flag illegal landlord behaviors.\n"
                        "2. IMMEDIATE STEP-BY-STEP ACTION PLAN: Give a sequential checklist of what the tenant needs to do right now.\n"
                        "3. REGIONAL LEGAL AID GROUPS: Point the tenant toward real groups operating in their specific city.\n"
                        "4. OFFICIAL LEGAL & SELF-HELP LINKS: Append the following verified reference links at the very end:\n"
                        "   - California Landlord/Tenant Guide Handbook: https://dre.ca.gov/files/pdf/2025_Landlord_Tenant_Guide.pdf\n"
                        "   - LawHelpCA Housing Issues Portal: https://www.lawhelpca.org/issues/housing/landlord-and-tenant-issues\n"
                        "   - California Courts Self-Help & Center Finder: https://selfhelp.courts.ca.gov/self-help/find-self-help?s=san%20francisco&id=4203\n"
                        "   - California Department of Real Estate (DRE): https://dre.ca.gov/\n\n"
                        "Disclaimer: Conclude with a notice that this is for educational purposes only."
                    )

                    prompt_contents = [f"Title: {issue_title}\nBody: {issue_body}"]
                    if image_object:
                        prompt_contents.append(image_object)

                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2
                        )
                    )
                    ai_analysis = response.text

                    # Save results to Neon
                    cur.execute("""
                        INSERT INTO chat_sessions (metadata)
                        VALUES (%s)
                        RETURNING session_id;
                    """, [psycopg.types.json.Jsonb({
                        "source": "streamlit_web_app",
                        "title": issue_title,
                        "has_attached_image": image_object is not None
                    })])
                    session_id = cur.fetchone()[0]
                    
                    cur.execute("""
                        INSERT INTO chat_messages (session_id, role, content)
                        VALUES (%s, 'model', %s);
                    """, (session_id, ai_analysis))
                    
                    conn.commit()

                    st.success("✅ Analysis Complete! Data saved securely.")
                    st.markdown(ai_analysis)

        except Exception as e:
            st.error(f"❌ Error during processing: {e}")

# 5. TRIGGER ONLY ON BUTTON CLICK
if st.button("Analyze Situation & Get Help", type="primary"):
    if not issue_title or not issue_body:
        st.warning("⚠️ Please fill out both the Title and Description fields before submitting.")
    else:
        run_housing_ai()