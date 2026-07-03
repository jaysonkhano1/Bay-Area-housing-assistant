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

            # 2. Instruct Gemini to act as a solution-oriented advisor and enforce the user's specific links
            print("🧠 Running issue text through Gemini Solution Engine...")
            system_instruction = (
                "You are the Bay Area Housing Stability Assistant, an expert AI legal information companion specializing in tenant rights in the San Francisco Bay Area.\n\n"
                "Your primary mission is to provide an accurate, clear, and actionable solution to the tenant's crisis—do NOT just summarize the issue. Analyze the provided housing issue (Title and Body) and structure your response as follows:\n\n"
                "1. CRITICAL ASSESSMENT & SOLUTION: Directly analyze the specific crisis (e.g., flag illegal landlord behaviors like self-help lockouts, address notice timeline calculations, or explain rules like 'repair and deduct' if applicable). Provide concrete educational guidance on how this specific problem is handled under California and local city rules.\n"
                "2. IMMEDIATE STEP-BY-STEP ACTION PLAN: Give a sequential, practical checklist of what the tenant needs to do right now to defend their housing stability and protect their rights.\n"
                "3. REGIONAL LEGAL AID GROUPS: Point the tenant toward real, community-based legal aid groups operating in their specific city or county (e.g., Silicon Valley, East Bay, or San Francisco).\n"
                "4. OFFICIAL LEGAL & SELF-HELP LINKS: You MUST explicitly append the following verified reference links at the very end of your response, formatting them clearly as Markdown links:\n"
                "   - California Landlord/Tenant Guide Handbook: https://dre.ca.gov/files/pdf/2025_Landlord_Tenant_Guide.pdf\n"
                "   - LawHelpCA Housing Issues Portal: https://www.lawhelpca.org/issues/housing/landlord-and-tenant-issues\n"
                "   - California Courts Self-Help & Center Finder: https://selfhelp.courts.ca.gov/self-help/find-self-help?s=san%20francisco&id=4203\n"
                "   - California Department of Real Estate (DRE): https://dre.ca.gov/\n\n"
                "Disclaimer: Conclude with a clear notice that this information is for operational guidance and educational purposes only, and does not constitute formal legal counsel."
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Title: {ISSUE_TITLE}\nBody: {ISSUE_BODY}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2
                )
            )
            ai_analysis = response.text

            # 3. Drop data into our persistence tables
            print("📝 Storing actionable solution into Neon...")
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