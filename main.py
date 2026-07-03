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

            # 2. Ask Gemini to clean and structure the data using the current SDK
            print("🧠 Running issue text through Gemini AI...")
            system_instruction = (
                "You are an AI processing assistant for the Bay Area Housing Stability Assistant.\n"
                "Take the user issue layout and clean it into a professional, brief summary."
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Title: {ISSUE_TITLE}\nBody: {ISSUE_BODY}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0
                )
            )
            ai_summary = response.text

            # 3. Drop data into our persistence tables
            print("📝 Storing AI summary into Neon...")
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
            """, (session_id, ai_summary))
            
            conn.commit()
            print(f"✅ Success! Saved to Neon under Session UUID: {session_id}")

if __name__ == "__main__":
    run_housing_ai()