"""
app.py — Streamlit Web Frontend for Engineering Email Intelligence Tool.
Premium dark-themed UI with interactive visualizations, email thread viewer.
"""

import streamlit as st
import os
import html as html_mod
import tempfile
import yaml
import datetime
from pathlib import Path
import pandas as pd
import time
import re

# Import our core modules
from ingestion.msg_parser import EmailRecord, parse_msg_file
from ingestion.eml_parser import parse_eml_file
from processing.cleaner import clean_email_body
from processing.deduplicator import deduplicate_body
from processing.spec_extractor import extract_all_specs
from processing.sentence_tagger import tag_sentences, extract_unresolved
from processing.summarizer import generate_summary
from processing.nlp_summary import generate_extractive_summary
from processing.local_ai import generate_local_summary, check_ollama_status
from main import build_people_table, build_timeline, load_config
from output.report_docx import generate_docx_report
from output.report_excel import generate_excel_report
from output.report_html import generate_html_report
import plotly.express as px
import pandas as pd

# ── STREAMLIT CONFIG ──
st.set_page_config(
    page_title="Eng Email Intel",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── PREMIUM DARK THEME CSS ──
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Global */
    .stApp {
        font-family: 'Inter', sans-serif;
    }
    .main .block-container {
        padding-top: 1.5rem;
        max-width: 1200px;
    }

    /* Header */
    .app-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(99, 102, 241, 0.2);
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .app-header h1 {
        color: #e2e8f0;
        font-size: 2rem;
        margin: 0;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .app-header p {
        color: #94a3b8;
        font-size: 0.95rem;
        margin: 0.5rem 0 0 0;
    }

    /* Metric Cards */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin: 1.5rem 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.15);
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(99, 102, 241, 0.15);
    }
    .metric-card .value {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .metric-card .label {
        font-size: 0.75rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-top: 0.3rem;
    }
    .metric-card.alert .value {
        background: linear-gradient(135deg, #ef4444, #f97316);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* Summary box */
    .summary-box {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        border-left: 4px solid #6366f1;
        margin: 1rem 0;
        color: #cbd5e1;
        line-height: 1.7;
        font-size: 0.92rem;
    }
    .summary-box h2, .summary-box h3 {
        color: #e2e8f0 !important;
        border: none !important;
    }
    .summary-box strong {
        color: #a5b4fc;
    }

    /* Email thread card */
    .email-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.1);
        margin-bottom: 1rem;
        transition: border-color 0.2s;
    }
    .email-card:hover {
        border-color: rgba(99, 102, 241, 0.4);
    }
    .email-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.75rem;
    }
    .email-sender {
        font-weight: 600;
        color: #a5b4fc;
        font-size: 0.95rem;
    }
    .email-date {
        color: #64748b;
        font-size: 0.8rem;
    }
    .email-subject {
        color: #e2e8f0;
        font-size: 0.9rem;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }
    .email-body-preview {
        color: #94a3b8;
        font-size: 0.85rem;
        line-height: 1.6;
        white-space: pre-wrap;
        max-height: 150px;
        overflow-y: auto;
    }
    .email-recipients {
        color: #64748b;
        font-size: 0.78rem;
        margin-top: 0.5rem;
    }

    /* Unresolved items */
    .unresolved-card {
        background: linear-gradient(135deg, #1e293b, #1a1a2e);
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #ef4444;
        margin-bottom: 0.75rem;
        color: #cbd5e1;
    }
    .unresolved-card .person {
        color: #f87171;
        font-weight: 600;
    }
    .unresolved-card .quote {
        font-style: italic;
        color: #94a3b8;
        margin: 0.5rem 0;
    }
    .unresolved-card .meta {
        color: #64748b;
        font-size: 0.78rem;
    }

    /* Spec highlight */
    mark {
        background: rgba(99, 102, 241, 0.3);
        color: #e2e8f0;
        padding: 1px 4px;
        border-radius: 3px;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a, #1e293b);
    }
    [data-testid="stSidebar"] .stMarkdown, 
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 {
        color: #e2e8f0;
    }

    /* Status indicator */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .status-ready {
        background: rgba(34, 197, 94, 0.15);
        color: #22c55e;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .status-pending {
        background: rgba(234, 179, 8, 0.15);
        color: #eab308;
        border: 1px solid rgba(234, 179, 8, 0.3);
    }
    /* Streamlit alert overrides for dark theme */
    .stAlert {
        background: linear-gradient(135deg, #1e293b, #0f172a) !important;
        color: #cbd5e1 !important;
        border: 1px solid rgba(99, 102, 241, 0.15) !important;
    }
    .stAlert > div {
        color: #cbd5e1 !important;
    }
    div[data-testid="stExpander"] {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 12px;
    }
    div[data-testid="stExpander"] summary {
        color: #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)


# ── PROCESSING PIPELINE ──
def process_uploaded_files(uploaded_files, config):
    """Save uploaded files to a temp dir and process them using our pipeline."""
    emails = []

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        errors = []
        for uploaded_file in uploaded_files:
            file_path = os.path.join(temp_dir, uploaded_file.name)
            try:
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                record = None
                if uploaded_file.name.lower().endswith(".msg"):
                    try:
                        record = parse_msg_file(file_path)
                    except Exception as e:
                        import traceback
                        err_msg = f"Failed to parse msg {uploaded_file.name}: {e}\n{traceback.format_exc()}"
                        print(err_msg)
                        errors.append(err_msg)
                elif uploaded_file.name.lower().endswith(".eml"):
                    try:
                        record = parse_eml_file(file_path)
                    except Exception as e:
                        import traceback
                        err_msg = f"Failed to parse eml {uploaded_file.name}: {e}\n{traceback.format_exc()}"
                        print(err_msg)
                        errors.append(err_msg)

                if record:
                    emails.append(record)
            except Exception as e:
                import traceback
                err_msg = f"Failed processing file {uploaded_file.name}: {e}\n{traceback.format_exc()}"
                print(err_msg)
                errors.append(err_msg)

        if not emails:
            return {"error": "\n\n".join(errors)} if errors else None

        # Sort by date
        emails.sort(key=lambda e: e.date or datetime.datetime.min)

        # 2. Clean & Deduplicate
        seen_hashes = set()
        for record in emails:
            record.body = clean_email_body(
                record.body,
                config.get("signature_markers", []),
                config.get("disclaimer_phrases", []),
            )
            record.body = deduplicate_body(record.body, seen_hashes)

        # 3. Extract Specs & Sentences
        all_specs = []
        specs_by_email = {}
        all_tagged = []
        all_unresolved = []

        for record in emails:
            email_specs = extract_all_specs(
                text=record.body,
                material_keywords=config.get("materials", []),
                sender_name=record.sender_name,
                sender_email=record.sender_email,
                date_str=record.date_str,
                source_file=record.source_file,
            )
            all_specs.extend(email_specs)
            specs_by_email[record.message_id] = email_specs

            tagged = tag_sentences(
                text=record.body,
                engineering_keywords=config.get("engineering_keywords", []),
                unresolved_markers=config.get("unresolved_markers", []),
                sender_name=record.sender_name,
                sender_email=record.sender_email,
                date_str=record.date_str,
                source_file=record.source_file,
            )
            all_tagged.extend(tagged)

            unresolved = extract_unresolved(
                text=record.body,
                unresolved_markers=config.get("unresolved_markers", []),
                sender_name=record.sender_name,
                sender_email=record.sender_email,
                date_str=record.date_str,
                source_file=record.source_file,
            )
            all_unresolved.extend(unresolved)

        # 4. People & Timeline
        people = build_people_table(emails, specs_by_email, config.get("role_keywords", []))
        timeline = build_timeline(all_specs, all_tagged)

        # 5. Executive Summary
        summary = generate_summary(emails, all_specs, people, all_unresolved, timeline)

        return {
            "emails": emails,
            "specs": all_specs,
            "people": people,
            "tagged": all_tagged,
            "unresolved": all_unresolved,
            "timeline": timeline,
            "summary": summary
        }


def generate_downloadable_reports(data):
    """Generate DOCX and XLSX in a temp dir for downloading."""
    temp_dir = tempfile.mkdtemp()

    docx_path = os.path.join(temp_dir, "Engineering_Report.docx")
    generate_docx_report(
        docx_path, data["people"], data["specs"],
        data["tagged"], data["unresolved"], data["timeline"]
    )

    xlsx_path = os.path.join(temp_dir, "Engineering_Report.xlsx")
    generate_excel_report(
        xlsx_path, data["people"], data["specs"],
        data["tagged"], data["unresolved"], data["timeline"]
    )

    return docx_path, xlsx_path


# ── HELPER: parse numeric values safely ──
def _parse_val(v):
    try:
        return float(str(v).replace(',', ''))
    except (ValueError, TypeError):
        return 0.0


def _sanitize_body(text: str) -> str:
    """Escape HTML and fix unicode escape sequences for safe display."""
    if not text:
        return "(empty)"
    # Decode any raw unicode escapes like \u00a0, \u2019, etc.
    try:
        text = text.encode('utf-8').decode('unicode_escape', errors='replace')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    # Strip common leftover escapes
    import re
    text = re.sub(r'\\u[0-9a-fA-F]{4}', '', text)
    # HTML-escape so no tags leak through
    text = html_mod.escape(text)
    return text


# ═══════════════════════════════════════════════════════════════
#  UI LAYOUT
# ═══════════════════════════════════════════════════════════════

config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config = load_config(config_path)

# ── Header ──
st.markdown("""
<div class="app-header">
    <h1>⚙️ Engineering Email Intelligence</h1>
    <p>Upload .msg or .eml files to automatically extract specifications, map participants, and surface action items.</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──
with st.sidebar:
    st.markdown("### 📁 Upload Files")
    uploaded_files = st.file_uploader(
        "Drop email files here",
        type=["msg", "eml"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Status indicator
    if uploaded_files:
        st.markdown('<span class="status-badge status-ready">✓ Files Loaded</span>', unsafe_allow_html=True)
        st.caption(f"{len(uploaded_files)} file(s) ready for analysis")
    else:
        st.markdown('<span class="status-badge status-pending">⏳ Awaiting Files</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📂 Supported Categories")
    categories_list = [
        "📐 Dimensions", "🔧 Torque", "⚡ Speed/RPM", "💪 Power",
        "🌡️ Pressure", "🌡️ Temperature", "⚡ Voltage", "🔌 Current",
        "⚖️ Weight/Mass", "📏 Tolerance", "🔩 Thread/Bolt",
        "🧱 Materials", "📜 Standards", "🛡️ IP Rating"
    ]
    for cat in categories_list:
        st.markdown(f"<small style='color:#94a3b8'>{cat}</small>", unsafe_allow_html=True)

    st.markdown("---")

    # Ollama / AI connection settings
    st.markdown("### 🤖 AI Settings")
    ollama_enabled = st.toggle("Enable Ollama (Local LLM)", value=False,
                               help="Toggle on if you have Ollama running locally")
    if ollama_enabled:
        ollama_url = st.text_input("Ollama URL", value="http://localhost:11434",
                                   help="Default: http://localhost:11434")
        st.session_state.ollama_url = ollama_url
        
        # dynamic selectbox to prevent typos
        available_models = ["llama3:latest", "deepseek-r1:14b", "gpt-oss:20b", "gpt-oss:120b"]
        st.selectbox("Ollama Model", options=available_models, index=1, key="ollama_model",
                     help="Select the exact model you want to run.")
        
        st.session_state.ollama_enabled = True
        # Check status
        if check_ollama_status(base_url=ollama_url):
            st.markdown('<span class="status-badge status-ready">✓ Ollama Connected</span>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-pending">✗ Not Reachable</span>',
                        unsafe_allow_html=True)
            st.caption("Ensure Ollama is running and accessible.")
    else:
        st.session_state.ollama_enabled = False
        st.caption("Using Python NLP (no LLM needed)")

# ── Main Content ──
if uploaded_files:
    with st.spinner('🔍 Analyzing emails...'):
        if "last_processed" not in st.session_state or st.session_state.last_processed != [f.name for f in uploaded_files]:
            data = process_uploaded_files(uploaded_files, config)
            if data and "error" in data:
                st.error("Failed to parse the uploaded files. Error details:")
                st.code(data["error"])
                st.stop()
            elif data:
                st.session_state.data = data
                st.session_state.last_processed = [f.name for f in uploaded_files]
                # Pre-generate reports
                docx_path, xlsx_path = generate_downloadable_reports(data)
                st.session_state.docx_path = docx_path
                st.session_state.xlsx_path = xlsx_path
            else:
                st.error("Could not parse the uploaded files (unknown error).")
                st.stop()
        else:
            data = st.session_state.data

    # ── Metrics Row ──
    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card">
            <div class="value">{len(data["emails"])}</div>
            <div class="label">Emails Analyzed</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(data["specs"])}</div>
            <div class="label">Specs Extracted</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(data["people"])}</div>
            <div class="label">Participants</div>
        </div>
        <div class="metric-card alert">
            <div class="value">{len(data["unresolved"])}</div>
            <div class="label">Open Items</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Summary Section ──
    st.markdown(f'<div class="summary-box">{data["summary"]}</div>', unsafe_allow_html=True)

    # NLP Summary / Ollama button
    col_sum, _ = st.columns([1, 3])
    with col_sum:
        is_ollama = st.session_state.get("ollama_enabled", False)
        btn_text = "🤖 Generate AI Summary (Ollama)" if is_ollama else "📝 Generate Detailed Summary (Python NLP)"
        
        if st.button(btn_text):
            start_time = time.time()
            with st.spinner("Analyzing email thread... (This may take several minutes for large models)"):
                if is_ollama:
                    raw_summary = generate_local_summary(
                        data["emails"], 
                        data["specs"], 
                        data["people"], 
                        data["unresolved"],
                        base_url=st.session_state.get("ollama_url", "http://localhost:11434"),
                        model_name=st.session_state.get("ollama_model", "llama3")
                    )
                else:
                    raw_summary = generate_extractive_summary(
                        data["emails"], data["specs"], data["people"], data["unresolved"]
                    )
                
                st.session_state.raw_detailed_summary = raw_summary
                st.session_state.detailed_summary_time = time.time() - start_time

    # Display the Detailed Summary Full-Width
    if "raw_detailed_summary" in st.session_state:
        raw_summary = st.session_state.raw_detailed_summary
        time_taken = st.session_state.get("detailed_summary_time", 0.0)
        
        # Check for <think> tags (Reasoning Models like DeepSeek R1)
        think_match = re.search(r"<think>(.*?)</think>", raw_summary, re.DOTALL)
        if think_match:
            thoughts = think_match.group(1).strip()
            final_answer = re.sub(r"<think>.*?</think>", "", raw_summary, flags=re.DOTALL).strip()
            with st.expander(f"🧠 AI Thought Process ({time_taken:.1f} seconds)"):
                st.markdown(f"_{thoughts}_")
            st.markdown(f'<div class="summary-box">{final_answer}</div>', unsafe_allow_html=True)
        else:
            st.caption(f"Generation time: {time_taken:.1f} seconds")
            st.markdown(f'<div class="summary-box">{raw_summary}</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    #  TABS
    # ═══════════════════════════════════════════════════════════════
    tab_conv, tab_specs, tab_viz, tab_open, tab_people, tab_export, tab_chat = st.tabs([
        "📧 Conversation", "📋 Specifications", "📈 Visualizations",
        "⚠️ Open Items", "👥 People", "💾 Export", "💬 Chat (AI)"
    ])

    # ── TAB: Conversation Thread ──
    with tab_conv:
        st.subheader("📧 Email Thread")
        if data["emails"]:
            for email in data["emails"]:
                date_display = email.date.strftime("%b %d, %Y at %I:%M %p") if email.date else "Unknown Date"
                recipients_str = ", ".join(email.recipients[:3])
                if len(email.recipients) > 3:
                    recipients_str += f" +{len(email.recipients) - 3} more"

                body_preview = _sanitize_body(email.body[:500]) if email.body else "(empty)"

                st.markdown(f"""
                <div class="email-card">
                    <div class="email-header">
                        <span class="email-sender">👤 {email.sender_name or email.sender_email}</span>
                        <span class="email-date">{date_display}</span>
                    </div>
                    <div class="email-subject">📌 {email.subject}</div>
                    <div class="email-body-preview">{body_preview}</div>
                    <div class="email-recipients">To: {recipients_str}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No emails to display.")

    # ── TAB: Specifications ──
    with tab_specs:
        st.subheader("📋 Extracted Specifications")
        if data["specs"]:
            # Build dataframe
            spec_data = []
            for s in data["specs"]:
                spec_data.append({
                    "Category": s.category,
                    "Subject": getattr(s, 'subject', '') or '—',
                    "Value": s.value,
                    "Unit": s.unit or '—',
                    "Mentioned By": s.mentioned_by,
                })
            df_specs_table = pd.DataFrame(spec_data)
            st.dataframe(df_specs_table, use_container_width=True, hide_index=True)

            st.markdown("#### 🔎 Detailed Context")
            for s in data["specs"]:
                subject_label = getattr(s, 'subject', '') or 'Unknown'
                label = f"**{s.category}** → {subject_label}: {s.value} {s.unit}  _(by {s.mentioned_by})_"
                with st.expander(label):
                    highlighted = s.context.replace(
                        s.raw_match, f"<mark>{s.raw_match}</mark>"
                    )
                    st.markdown(f"> {highlighted}", unsafe_allow_html=True)
        else:
            st.info("No specifications detected in these emails.")

    # ── TAB: Visualizations ──
    with tab_viz:
        st.subheader("📈 Engineering Specification Analysis")
        if data["specs"]:
            df_viz = pd.DataFrame([{
                "Category": s.category,
                "Subject": getattr(s, 'subject', '') or '—',
                "Value": _parse_val(s.value),
                "Unit": s.unit or '',
                "Mentioned By": s.mentioned_by,
                "Display": f"{getattr(s, 'subject', '') or s.category}: {s.value} {s.unit}".strip()
            } for s in data["specs"]])

            df_numeric = df_viz[df_viz["Value"] > 0]

            if not df_numeric.empty:
                _dark_layout = dict(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_color='#94a3b8',
                    title_font_color='#e2e8f0',
                    xaxis=dict(gridcolor='rgba(99,102,241,0.08)'),
                    yaxis=dict(gridcolor='rgba(99,102,241,0.08)'),
                    legend=dict(font=dict(color='#94a3b8'))
                )

                # Chart 1: Horizontal bar — specs grouped by Subject with labeled values
                fig_hbar = px.bar(
                    df_numeric.sort_values("Value", ascending=True),
                    y="Display", x="Value", color="Category",
                    orientation='h',
                    title="All Extracted Values (grouped by what they describe)",
                    hover_data=["Unit", "Mentioned By"],
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    text="Value"
                )
                fig_hbar.update_traces(texttemplate='%{text:.4g}', textposition='outside')
                fig_hbar.update_layout(**_dark_layout, height=max(350, len(df_numeric) * 35))
                st.plotly_chart(fig_hbar, use_container_width=True)

                # Chart 2: Category breakdown
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    cat_counts = df_viz["Category"].value_counts().reset_index()
                    cat_counts.columns = ["Category", "Count"]
                    fig_pie = px.pie(
                        cat_counts, names="Category", values="Count",
                        title="Specification Categories Found",
                        color_discrete_sequence=px.colors.sequential.Purples_r,
                        hole=0.45
                    )
                    fig_pie.update_layout(**_dark_layout)
                    st.plotly_chart(fig_pie, use_container_width=True)

                with col_c2:
                    # Who contributed the most specs
                    contrib = df_viz.groupby("Mentioned By").size().reset_index(name="Specs")
                    contrib = contrib.sort_values("Specs", ascending=True)
                    fig_contrib = px.bar(
                        contrib, y="Mentioned By", x="Specs",
                        orientation='h',
                        title="Specs Contributed per Person",
                        color_discrete_sequence=['#8b5cf6']
                    )
                    fig_contrib.update_layout(**_dark_layout)
                    st.plotly_chart(fig_contrib, use_container_width=True)
            else:
                st.info("No numeric values to visualize.")
        else:
            st.info("No data available for visualization.")

    # ── TAB: Open Items ──
    with tab_open:
        st.subheader("⚠️ Action Items & Unresolved Queries")
        if data["unresolved"]:
            for item in data["unresolved"]:
                flags = ', '.join(item.trigger_keywords) if item.trigger_keywords else '—'
                st.markdown(f"""
                <div class="unresolved-card">
                    <span class="person">{item.mentioned_by}</span> said:<br>
                    <div class="quote">"{item.sentence}"</div>
                    <div class="meta">🏷️ Flags: {flags} &nbsp;|&nbsp; 📅 {item.date_str}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ No unresolved items or pending decisions found!")

    # ── TAB: People ──
    with tab_people:
        st.subheader("👥 People Involved")
        if data["people"]:
            df_people = pd.DataFrame(data["people"])
            # Clean up specs_mentioned for display
            if "specs_mentioned" in df_people.columns:
                df_people["specs_mentioned"] = df_people["specs_mentioned"].apply(
                    lambda x: ", ".join(x[:5]) + ("..." if len(x) > 5 else "") if isinstance(x, list) else str(x)
                )
            st.dataframe(df_people, use_container_width=True, hide_index=True)
        else:
            st.info("No participants found.")

    # ── TAB: Export ──
    with tab_export:
        st.subheader("💾 Export Reports")
        st.markdown("Download the extracted intelligence in your preferred format.")

        col_btn1, col_btn2, col_btn3 = st.columns(3)

        with col_btn1:
            if "docx_path" in st.session_state:
                with open(st.session_state.docx_path, "rb") as file:
                    st.download_button(
                        label="📄 Download Word (.docx)",
                        data=file,
                        file_name="Engg_Intel_Report.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )

        with col_btn2:
            if "xlsx_path" in st.session_state:
                with open(st.session_state.xlsx_path, "rb") as file:
                    st.download_button(
                        label="📊 Download Excel (.xlsx)",
                        data=file,
                        file_name="Engg_Intel_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

        with col_btn3:
            st.info("Exports Generated Successfully")

    # ── TAB: Chatbot ──
    with tab_chat:
        st.subheader("💬 Chat with AI (Context-Aware)")
        st.caption("Ask questions about this specific engineering email thread.")

        if not st.session_state.get("ollama_enabled", False):
            st.warning("Please enable Ollama in the left sidebar to use the chatbot!")
        else:
            # Initialize chat history uniquely for this email thread
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []
                
            # Render existing chat
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    content = msg["content"]
                    think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
                    if think_match:
                        with st.expander("🧠 AI Thought Process"):
                            st.markdown(f"_{think_match.group(1).strip()}_")
                        final = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                        st.markdown(final)
                    else:
                        st.markdown(content)
            
            # Chat input
            if prompt_text := st.chat_input("Ask a question about the dimensions or project..."):
                # Append user message
                st.session_state.chat_history.append({"role": "user", "content": prompt_text})
                with st.chat_message("user"):
                    st.markdown(prompt_text)
                
                # Generate AI response
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        from processing.local_ai import generate_chat_response
                        raw_reply = generate_chat_response(
                            messages=st.session_state.chat_history,
                            emails=data["emails"],
                            specs=data["specs"],
                            people=data["people"],
                            base_url=st.session_state.get("ollama_url", "http://localhost:11434"),
                            model_name=st.session_state.get("ollama_model", "llama3:latest")
                        )
                        
                        # Display
                        think_match = re.search(r"<think>(.*?)</think>", raw_reply, re.DOTALL)
                        if think_match:
                            with st.expander("🧠 AI Thought Process"):
                                st.markdown(f"_{think_match.group(1).strip()}_")
                            final = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.DOTALL).strip()
                            st.markdown(final)
                        else:
                            st.markdown(raw_reply)
                        
                        # Save
                        st.session_state.chat_history.append({"role": "assistant", "content": raw_reply})

else:
    # ── Empty State ──
    st.markdown("""
    <div style="text-align: center; padding: 4rem 2rem;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📧</div>
        <h2 style="color: #e2e8f0; font-weight: 600;">No Emails Uploaded Yet</h2>
        <p style="color: #94a3b8; font-size: 1.05rem; max-width: 500px; margin: 0 auto;">
            Upload <code>.msg</code> or <code>.eml</code> files in the sidebar to begin extracting
            engineering specifications, mapping participants, and surfacing action items.
        </p>
    </div>
    """, unsafe_allow_html=True)
