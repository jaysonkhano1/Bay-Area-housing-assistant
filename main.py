import os
import psycopg
from google import generativeai as genai

# 1. Grab environment details automatically provided by GitHub & Neon
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "No Title Provided")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "No Content Provided")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

def run_housing_ai():
    print("🚀 GitHub Action triggered! Processing housing entry...")

    # 2. Ask Gemini to clean and structure the data (Deterministic extraction)
    system_instruction = (
        "You are an AI processing assistant for the Bay Area Housing Stability Assistant.\n"
        "Take the user issue layout and clean it into a professional, brief summary."
    )
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={"temperature": 0.0}
    )
    
    response = model.generate_content([system_instruction, f"Title: {ISSUE_TITLE}\nBody: {ISSUE_BODY}"])
    ai_summary = response.text

    # 3. Connect directly to Neon Postgres and persist the entry
    print("💾 Connecting to Neon Postgres database...")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Drop into our persistence tracking tables
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
    if not DATABASE_URL or not GEMINI_API_KEY:
        print("❌ Error: Missing configuration secrets.")
    else:
        run_housing_ai()