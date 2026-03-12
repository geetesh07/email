"""
app.py — Streamlit Web Frontend for Engineering Email Intelligence Tool.
"""

import streamlit as st
import os
import tempfile
import yaml
from pathlib import Path

# Import our core modules
from ingestion.msg_parser import EmailRecord, parse_msg_file
from ingestion.eml_parser import parse_eml_file
from processing.cleaner import clean_email_body
from processing.deduplicator import deduplicate_body
from processing.spec_extractor import extract_all_specs
from processing.sentence_tagger import tag_sentences, extract_unresolved
from processing.summarizer import generate_summary
from main import build_people_table, build_timeline, load_config
from output.report_docx import generate_docx_report
from output.report_excel import generate_excel_report
from output.report_html import generate_html_report

# ── STREAMLIT CONFIG ──
st.set_page_config(
    page_title="Eng Email Intel",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a better UI look
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6;
    }
    .main .block-container {
        padding-top: 2rem;
    }
    h1 {
        color: #1a3c6e;
    }
    h2 {
        color: #2d7dd2;
        border-bottom: 2px solid #2d7dd2;
        padding-bottom: 5px;
    }
    .metric-box {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        border-left: 5px solid #2d7dd2;
    }
    .metric-value {
        font-size: 28px;
        font-weight: bold;
        color: #1a3c6e;
    }
    .metric-label {
        font-size: 14px;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .unresolved-alert {
        padding: 15px;
        background-color: #fff5f5;
        border-left: 5px solid #cc3333;
        margin-bottom: 15px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)


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
        emails.sort(key=lambda e: e.date or __import__("datetime").datetime.min)

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
            # Specs
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

            # Sentences & Unresolved
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

# ── UI LAYOUT ──
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config = load_config(config_path)

st.title("⚙️ Engineering Email Intelligence")
st.markdown("Upload a thread of `.msg` or `.eml` files to automatically extract specifications, map participants, and identify action items.")

with st.sidebar:
    st.header("Upload Files")
    uploaded_files = st.file_uploader(
        "Drop email files here", 
        type=["msg", "eml"], 
        accept_multiple_files=True
    )
    
    st.markdown("---")
    st.markdown("### Supported Categories")
    st.markdown("- Dimensions\n- Torque, Speed, Power\n- Pressure, Temperature\n- Voltage, Current\n- Weight/Mass\n- Tolerance\n- Thread/Bolt\n- Materials\n- Standards\n- IP Rating / Options")

if uploaded_files:
    with st.spinner('Analyzing emails...'):
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

    # --- Dashboards ---
    st.header("📊 Executive Summary")
    st.markdown(data["summary"], unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="metric-box"><div class="metric-value">{len(data["emails"])}</div><div class="metric-label">Emails Analyzed</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-box"><div class="metric-value">{len(data["specs"])}</div><div class="metric-label">Specs Found</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-box"><div class="metric-value">{len(data["people"])}</div><div class="metric-label">Participants</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-box"><div class="metric-value">{len(data["unresolved"])}</div><div class="metric-label" style="color:#cc3333;">Open Items</div></div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Specifications", "⚠️ Open Items", "👥 People", "💾 Export Reports"])
    
    with tab1:
        st.subheader("Extracted Specifications")
        if data["specs"]:
            spec_data = []
            for s in data["specs"]:
                spec_data.append({
                    "Category": s.category,
                    "Value": f"{s.value} {s.unit}".strip(),
                    "Mentioned By": s.mentioned_by,
                    "Context": s.context
                })
            st.dataframe(spec_data, use_container_width=True)
        else:
            st.info("No specifications detected in these emails.")

    with tab2:
        st.subheader("Action Items & Unresolved Queries")
        if data["unresolved"]:
            for item in data["unresolved"]:
                st.markdown(f"""
                <div class="unresolved-alert">
                    <strong>{item.mentioned_by}</strong> ask/said:<br>
                    <em>"{item.sentence}"</em><br>
                    <small>Flags: {', '.join(item.trigger_keywords)} | Date: {item.date_str}</small>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No unresolved items or pending decisions found!")

    with tab3:
        st.subheader("People Involved")
        if data["people"]:
            st.dataframe(data["people"], use_container_width=True)
            
    with tab4:
        st.subheader("Download Full Reports")
        st.markdown("Download the extracted intelligence in your preferred format.")
        
        col_btn1, col_btn2, _ = st.columns([1, 1, 3])
        
        with col_btn1:
            with open(st.session_state.docx_path, "rb") as file:
                btn = st.download_button(
                    label="📄 Download Word (.docx)",
                    data=file,
                    file_name="Engg_Intel_Report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                
        with col_btn2:
            with open(st.session_state.xlsx_path, "rb") as file:
                btn = st.download_button(
                    label="📊 Download Excel (.xlsx)",
                    data=file,
                    file_name="Engg_Intel_Report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
else:
    st.info("👈 Please upload some .msg or .eml files in the sidebar to begin.")
