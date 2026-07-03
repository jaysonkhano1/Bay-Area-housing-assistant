import os
import sys
import psycopg

# Grab the database connection string
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("❌ Error: DATABASE_URL environment variable is missing in your terminal.")
    print("💡 Tip: Run 'export DATABASE_URL=\"your_connection_string\"' first.")
    sys.exit(1)

def fetch_latest_entries():
    try:
        print("💾 Connecting to Neon Postgres to verify data...")
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                
                # Fetch the most recent chat sessions and their linked AI messages
                cur.execute("""
                    SELECT s.session_id, s.created_at, s.metadata->>'title' AS title, m.role, m.content
                    FROM chat_sessions s
                    JOIN chat_messages m ON s.session_id = m.session_id
                    ORDER BY s.created_at DESC
                    LIMIT 3;
                """)
                
                rows = cur.fetchall()
                
                if not rows:
                    print("❓ Connected successfully, but found no records in the tables yet.")
                    return
                
                print(f"\n🎉 Success! Found {len(rows)} recent entries stored in Neon:\n")
                for row in rows:
                    session_id, created_at, title, role, content = row
                    print("=" * 60)
                    print(f"📅 Saved At: {created_at}")
                    print(f"🆔 Session ID: {session_id}")
                    print(f"📌 Issue Title: {title}")
                    print(f"👤 Role: {role}")
                    print(f"📝 AI Summary:\n{content.strip()}")
                    print("=" * 60 + "\n")

    except Exception as e:
        print(f"❌ Error connecting or querying database: {e}")

if __name__ == "__main__":
    fetch_latest_entries()