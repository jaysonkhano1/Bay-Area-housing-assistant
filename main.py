import streamlit as st
import os
import psycopg
import time
from google import genai
from google.genai import types
from PIL import Image

# 1. Advanced Page & Theme Configuration
st.set_page_config(
    page_title="Bay Area Housing Assistant", 
    page_icon="🏠", 
    layout="wide", # Expanded layout for dashboard feel
    initial_sidebar_state="collapsed"
)

# Inject Sleek Custom CSS UI Elements
st.markdown("""
    <style>
        .main-header {
            font-size: 2.6rem;
            font-weight: 800;
            background: linear-gradient(45deg, #1E88E5, #00E676);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.2rem;
        }
        .subtitle {
            font-size: 1.1rem;
            color: #888888;
            margin-bottom: 2rem;
        }
        div[data-testid="stExpander"] {
            border: 1px solid #262730;
            border-radius: 8px;
        }
        .report-card {
            background-color: #111217;
            padding: 20px;
            border-radius: 10px;
            border-left: 5px solid #1E88E5;
            line-height: 1.6;
        }
    </style>
""", unsafe_allow_html=True)

# App Branding Header
st.markdown('<p class="main-header">🏠 Bay Area Housing Stability Assistant</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Empowering tenants with RAG-verified legal insights, timelines, and regional community resources.</p>', unsafe_allow_html=True)

# 2. Grab Secrets Securely
DATABASE_URL = st.secrets.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not DATABASE_URL or not GEMINI_API_KEY:
    st.error("❌ Configuration secrets missing. Please add DATABASE_URL and GEMINI_API_KEY to your App Secrets.")
    st.stop()

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# 3. Create a clean Tab-based Interface
tab_analyze, tab_about = st.tabs(["🔍 Analyze Notice or Crisis", "ℹ️ How to Use & Disclaimers"])

with tab_analyze:
    # Modern Two-Column Workspace Layout
    col_input, col_preview = st.columns([3, 2], gap="large")
    
    with col_input:
        st.subheader("📋 Case Profile")
        issue_title = st.text_input(
            "Issue Headline", 
            placeholder="e.g., Received 3-Day Notice over water bill dispute in Oakland"
        )
        issue_body = st.text_area(
            "Detailed Situation", 
            placeholder="Paste the notice text or explain dates, rent amounts, landlord actions, or communication issues here...", 
            height=180
        )
        
    with col_preview:
        st.subheader("📷 Document Upload")
        uploaded_file = st.file_uploader(
            "Upload physical notice image (Optional)", 
            type=["png", "jpg", "jpeg"],
            help="Gemini will cross-reference text layout details directly from your photo."
        )
        
        image_object = None
        if uploaded_file:
            image_object = Image.open(uploaded_file)
            st.image(image_object, caption="📷 Loaded Document Preview", use_container_width=True)
        else:
            st.info("💡 Pro-Tip: You can upload smartphone photos of official letters to have the AI cross-examine timestamps automatically.")

    st.markdown("---")

    # 4. Define the Integrated AI & RAG Processing Engine
    def run_housing_ai():
        # Elegant multi-step status tracker
        with st.status("🚀 Processing housing assistance report...", expanded=True) as status:
            try:
                status.update(label="🔐 Connecting to Neon database (Handling serverless cold starts)...", state="running")
                conn = None
                max_retries = 3
                
                for attempt in range(max_retries):
                    try:
                        conn = psycopg.connect(DATABASE_URL, connect_timeout=15)
                        break 
                    except (psycopg.OperationalError, psycopg.Error) as db_err:
                        if attempt < max_retries - 1:
                            time.sleep(3)
                            continue
                        else:
                            raise db_err

                with conn:
                    with conn.cursor() as cur:
                        # Ensure baseline application metrics and history tracking exist
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

                        # ──── START RAG PIPELINE EXECUTIONS ────
                        status.update(label="🧠 Vectorizing case facts for matching...", state="running")
                        
                        # 1. Convert user parameters into a semantic vector search token
                        user_query_text = f"{issue_title} {issue_body}"
                        query_embedding_res = client.models.embed_content(
                            model="text-embedding-004",
                            contents=user_query_text
                        )
                        query_vector = query_embedding_res.embeddings[0].values

                        status.update(label="🔍 Matching against verified regional statutes inside Neon...", state="running")
                        
                        # 2. Extract the top 2 ground-truth legal facts via pgvector distance mapping (<=>)
                        cur.execute("""
                            SELECT legal_text, jurisdiction 
                            FROM legal_knowledge_base 
                            ORDER BY embedding <=> %s::vector 
                            LIMIT 2;
                        """, (query_vector,))

                        matched_rows = cur.fetchall()
                        
                        # Format the text bits we pulled from our vector table
                        if matched_rows:
                            retrieved_context = "\n\n".join([f"[{row[1]} Reference]: {row[0]}" for row in matched_rows])
                        else:
                            retrieved_context = "[No specific statutory local context matched. Defaulting to general California Tenant Guidelines.]"

                        status.update(label="🧠 Injecting legal reference constraints into Gemini...", state="running")
                        
                        # 3. Formulate structural boundaries powered by the real data context
                        system_instruction = (
                            "You are the Bay Area Housing Stability Assistant, an expert AI legal information companion specializing in tenant rights in the San Francisco Bay Area.\n\n"
                            "CRITICAL GROUND-TRUTH REFERENCES TO APPLY:\n"
                            f"{retrieved_context}\n\n"
                            "Your primary mission is to provide an accurate, clear, and actionable solution to the tenant's crisis using the local ground-truth rules above. "
                            "If the tenant's situation contains factual violations of the law (such as illegal late fees added to a 3-day notice), explicitly highlight it. "
                            "Do not guess or hallucinate regulations outside of verified state or municipal code parameters.\n\n"
                            "Structure your response precisely using these Markdown headers:\n\n"
                            "## 🔴 CRITICAL ASSESSMENT & TIMELINE\n"
                            "Analyze strict notice countdown windows, lease conditions, and point out any unauthorized or illegal landlord actions.\n\n"
                            "## ⚡ IMMEDIATE STEP-BY-STEP ACTION PLAN\n"
                            "Provide a clear, practical, bulleted checklist of exact steps the tenant must do right now.\n\n"
                            "## 🤝 REGIONAL LEGAL AID GROUPS\n"
                            "Provide real, local non-profit legal networks or tenant rights groups that operate in their specific jurisdiction.\n\n"
                            "## 🔗 OFFICIAL LEGAL LINKS\n"
                            "You MUST append these precise resource references as markdown links at the absolute end:\n"
                            "- California Landlord/Tenant Guide Handbook: https://dre.ca.gov/files/pdf/2025_Landlord_Tenant_Guide.pdf\n"
                            "- LawHelpCA Housing Issues Portal: https://www.lawhelpca.org/issues/housing/landlord-and-tenant-issues\n"
                            "- California Courts Self-Help Center: https://selfhelp.courts.ca.gov/\n\n"
                            "Disclaimer: Conclude with a clear notice that this information is for educational purposes only and does not constitute formal legal counsel."
                        )

                        # Set up contents (include picture context if present)
                        prompt_contents = [user_query_text]
                        if image_object:
                            prompt_contents.append(image_object)

                        # 4. Generate grounded completion at temperature 0.0
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt_contents,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                temperature=0.0
                            )
                        )
                        ai_analysis = response.text

                        # ──── END RAG PIPELINE EXECUTIONS ────

                        status.update(label="💾 Archiving interaction logs into history storage...", state="running")
                        
                        # Log the session metadata
                        cur.execute("""
                            INSERT INTO chat_sessions (metadata)
                            VALUES (%s)
                            RETURNING session_id;
                        """, [psycopg.types.json.Jsonb({
                            "source": "streamlit_rag_dashboard",
                            "title": issue_title,
                            "has_attached_image": image_object is not None
                        })])
                        session_id = cur.fetchone()[0]
                        
                        # Log the message body
                        cur.execute("""
                            INSERT INTO chat_messages (session_id, role, content)
                            VALUES (%s, 'model', %s);
                        """, (session_id, ai_analysis))
                        
                        conn.commit()

                status.update(label="🎯 Case Assessment Report Completed Successfully!", state="complete")
                
                # Visual celebration and markdown payout
                st.balloons()
                st.markdown("<br>", unsafe_allow_html=True)
                st.success("🔒 Secure Transaction complete. RAG-vetted advice generated below:")
                
                st.markdown(f'<div class="report-card">{ai_analysis}</div>', unsafe_allow_html=True)

            except Exception as e:
                status.update(label="💥 System Disruption Encountered", state="error")
                st.error(f"Execution Error Trace: {e}")

    # 5. Execution Trigger Code Block
    if st.button("Generate Case Analysis & Plan", type="primary", use_container_width=True):
        if not issue_title or not issue_body:
            st.warning("⚠️ Please fill out both the Title and Detailed Situation fields before running analysis.")
        else:
            run_housing_ai()

with tab_about:
    st.subheader("💡 Educational Scope & Architecture Guidance")
    st.info("""
        **System Blueprint:** This application combines an open-source relational database layer with localized vector similarity lookups to prevent Large Language Model hallucinations.
        
        **Data Processing Flow:** User constraints are indexed into continuous vector spaces, matched dynamically via PostgreSQL `pgvector` math models against indexed municipal ordinances, and wrapped inside customized system role profiles.
        
        **Legal Notice:** This utility functions purely as an educational workflow exploration tool. It does not provide legal representation.
    """)