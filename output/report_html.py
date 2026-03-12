"""
report_html.py — Generate a self-contained HTML report with embedded CSS.
"""

import os
from typing import List, Dict
from html import escape


def _html_header(title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<style>
  :root {{
    --primary: #1a3c6e;
    --accent: #2d7dd2;
    --danger: #cc3333;
    --bg: #f5f7fa;
    --card: #ffffff;
    --text: #2d3748;
    --muted: #718096;
    --border: #e2e8f0;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{
    color: var(--primary);
    font-size: 1.8rem;
    text-align: center;
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 3px solid var(--accent);
  }}
  .section {{
    background: var(--card);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid var(--border);
  }}
  .section h2 {{
    color: var(--primary);
    font-size: 1.3rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--accent);
    cursor: pointer;
    user-select: none;
  }}
  .section h2::before {{
    content: '▼ ';
    font-size: 0.8rem;
    color: var(--accent);
  }}
  .section h2.collapsed::before {{ content: '► '; }}
  .collapsible {{ transition: max-height 0.3s ease; overflow: hidden; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }}
  th {{
    background: var(--primary);
    color: white;
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
  }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
  }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  tr:hover {{ background: #edf2f7; }}
  .sentence-card {{
    padding: 0.8rem 1rem;
    margin: 0.5rem 0;
    border-left: 4px solid var(--accent);
    background: #f8fafc;
    border-radius: 0 8px 8px 0;
  }}
  .sentence-card.unresolved {{
    border-left-color: var(--danger);
    background: #fff5f5;
  }}
  .meta {{
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 0.3rem;
  }}
  .keywords {{
    display: inline-block;
    background: var(--accent);
    color: white;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 12px;
    margin-right: 4px;
  }}
  .badge-unresolved {{
    background: var(--danger);
    color: white;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 12px;
  }}
  .empty {{ color: var(--muted); font-style: italic; }}
  .stats {{
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
  }}
  .stat-card {{
    flex: 1;
    min-width: 120px;
    background: var(--card);
    border-radius: 12px;
    padding: 1rem;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid var(--border);
  }}
  .stat-card .number {{
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
  }}
  .stat-card .label {{
    font-size: 0.8rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
</style>
</head>
<body>
<div class="container">
<h1>{escape(title)}</h1>
"""


def _html_footer() -> str:
    return """
</div>
<script>
document.querySelectorAll('.section h2').forEach(h => {
  h.addEventListener('click', () => {
    const content = h.nextElementSibling;
    if (content.style.maxHeight) {
      content.style.maxHeight = null;
      h.classList.remove('collapsed');
    } else {
      content.style.maxHeight = '0';
      h.classList.add('collapsed');
    }
  });
});
</script>
</body>
</html>"""


def generate_html_report(
    output_path: str,
    people: List[Dict],
    specs: list,
    tagged_sentences: list,
    unresolved: list,
    timeline: list,
    title: str = "Engineering Email Intelligence Report",
):
    """Generate a self-contained HTML report."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    html = _html_header(title)

    # ── Summary Stats ──
    html += '<div class="stats">\n'
    html += f'<div class="stat-card"><div class="number">{len(people)}</div><div class="label">People</div></div>\n'
    html += f'<div class="stat-card"><div class="number">{len(specs)}</div><div class="label">Specs</div></div>\n'
    html += f'<div class="stat-card"><div class="number">{len(tagged_sentences)}</div><div class="label">Sentences</div></div>\n'
    html += f'<div class="stat-card"><div class="number">{len(unresolved)}</div><div class="label">Open Items</div></div>\n'
    html += '</div>\n'

    # ── People ──
    html += '<div class="section">\n<h2>People Involved</h2>\n<div class="collapsible">\n'
    if people:
        html += '<table><tr><th>Name</th><th>Email</th><th>Company</th><th>Role</th></tr>\n'
        for p in people:
            html += f'<tr><td>{escape(p.get("name", ""))}</td>'
            html += f'<td>{escape(p.get("email", ""))}</td>'
            html += f'<td>{escape(p.get("company", ""))}</td>'
            html += f'<td>{escape(p.get("role", ""))}</td></tr>\n'
        html += '</table>\n'
    else:
        html += '<p class="empty">No people data extracted.</p>\n'
    html += '</div></div>\n'

    # ── Specs ──
    html += '<div class="section">\n<h2>Extracted Specifications</h2>\n<div class="collapsible">\n'
    if specs:
        html += '<table><tr><th>Category</th><th>Value</th><th>Unit</th><th>Mentioned By</th><th>Date</th></tr>\n'
        for s in specs:
            html += f'<tr><td>{escape(s.category)}</td>'
            html += f'<td>{escape(s.value)}</td>'
            html += f'<td>{escape(s.unit)}</td>'
            html += f'<td>{escape(s.mentioned_by)}</td>'
            html += f'<td>{escape(s.date_str)}</td></tr>\n'
        html += '</table>\n'
    else:
        html += '<p class="empty">No specifications extracted.</p>\n'
    html += '</div></div>\n'

    # ── Engineering Sentences ──
    html += '<div class="section">\n<h2>Engineering-Relevant Sentences</h2>\n<div class="collapsible">\n'
    if tagged_sentences:
        for ts in tagged_sentences:
            cls = "sentence-card unresolved" if ts.is_unresolved else "sentence-card"
            html += f'<div class="{cls}">\n'
            for kw in ts.trigger_keywords:
                html += f'<span class="keywords">{escape(kw)}</span>\n'
            html += f'<p>{escape(ts.sentence)}</p>\n'
            html += f'<div class="meta">— {escape(ts.mentioned_by)} | {escape(ts.date_str)}</div>\n'
            html += '</div>\n'
    else:
        html += '<p class="empty">No engineering sentences flagged.</p>\n'
    html += '</div></div>\n'

    # ── Unresolved Items ──
    html += '<div class="section">\n<h2>Open / Unconfirmed Items</h2>\n<div class="collapsible">\n'
    if unresolved:
        for u in unresolved:
            html += '<div class="sentence-card unresolved">\n'
            html += '<span class="badge-unresolved">OPEN</span>\n'
            html += f'<p>"{escape(u.sentence)}"</p>\n'
            html += f'<div class="meta">— {escape(u.mentioned_by)} | {escape(u.date_str)}</div>\n'
            html += '</div>\n'
    else:
        html += '<p class="empty">No unresolved items found.</p>\n'
    html += '</div></div>\n'

    # ── Timeline ──
    html += '<div class="section">\n<h2>Timeline</h2>\n<div class="collapsible">\n'
    if timeline:
        html += '<table><tr><th>Date</th><th>Event / Sentence</th><th>Mentioned By</th></tr>\n'
        for t in timeline:
            html += f'<tr><td>{escape(t.get("date", ""))}</td>'
            html += f'<td>{escape(t.get("sentence", ""))}</td>'
            html += f'<td>{escape(t.get("mentioned_by", ""))}</td></tr>\n'
        html += '</table>\n'
    else:
        html += '<p class="empty">No timeline events extracted.</p>\n'
    html += '</div></div>\n'

    html += _html_footer()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✓ HTML report saved: {output_path}")
    return output_path
