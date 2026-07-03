import os
import sys
import psycopg
from google import genai
from google.genai import types

# Grab environment details
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "No Title Provided")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "No Content Provided")

if not DATABASE_URL or not GEMINI_API_KEY:
    print("❌ Error: Missing configuration secrets (DATABASE_URL or GEMINI_API_KEY).")
    sys.exit(1)

# Initialize the modern Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

def run_housing_ai():
    print("🚀 GitHub Action triggered! Processing housing entry...")

    # 1. Connect to Neon and ensure tables exist
    print("💾 Connecting to Neon Postgres database...")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            
            print("🔨 Checking/Creating required database tables...")
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

            # 2. Instruct Gemini to act as a highly specialized Bay Area housing advisor
            print("🧠 Running issue text through Gemini AI Advisor...")
            system_instruction = (
                "You are the Bay Area Housing Stability Assistant, an expert AI legal information companion specializing in tenant rights in the San Francisco Bay Area.\n\n"
                "Analyze the provided housing issue (Title and Body). Provide a comprehensive, structured, and compassionate breakdown that includes:\n"
                "1. SITUATION ASSESSMENT: Clearly state the detected city, the type of notice received, and the core conflict.\n"
                "2. LEGAL TIMELINES & RIGHTS: Explain specific tenant rights regarding this crisis under California and local city ordinances (e.g., clarify if weekends/holidays count toward their notice timeline, or rules on utility disputes).\n"
                "3. IMMEDIATE ACTION PLAN: Provide a step-by-step checklist of what the tenant should do right now to protect themselves.\n"
                "4. LOCAL BAY AREA RESOURCES: List real, highly relevant legal aid groups for their specific area (e.g., Centro Legal de la Raza or Eviction Defense Center for Oakland/Alameda County; OMC for San Francisco, etc.).\n\n"
                "Disclaimer: End with a clear statement that this is automated operational information, not formal legal advice."
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Title: {ISSUE_TITLE}\nBody: {ISSUE_BODY}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3  # Slightly higher for balanced, fluid advice generation
                )
            )
            ai_analysis = response.text

            # 3. Drop data into our persistence tables
            print("📝 Storing expert AI response into Neon...")
            cur.execute("""
                INSERT INTO chat_sessions (metadata)
                VALUES (%s)
                RETURNING session_id;
            """, [psycopg.types.json.Jsonb({
                "source": "github_automation",
                "title": ISSUE_TITLE
            })])
            session_id = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO chat_messages (session_id, role, content)
                VALUES (%s, 'model', %s);
            """, (session_id, ai_analysis))
            
            conn.commit()
            print(f"✅ Success! Saved comprehensive guide to Neon under Session UUID: {session_id}")

if __name__ == "__main__":
    run_housing_ai()