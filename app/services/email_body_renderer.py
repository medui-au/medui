"""Render patient email bodies: Markdown → HTML → sanitize → inline CSS → plain-text fallback.

Public API
----------
    render(source: str) -> RenderResult
        Auto-detect markdown/HTML/plain, convert and sanitize.
        Returns RenderResult(html, plain).
"""
from __future__ import annotations
import re
from dataclasses import dataclass

import bleach
import markdown as _md


_ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'span', 'div', 'img', 'sup', 'sub',
]
_ALLOWED_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    '*': ['class'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'width', 'height'],
    'td': ['colspan', 'rowspan', 'align'],
    'th': ['colspan', 'rowspan', 'align'],
}

_EMAIL_CSS = """
body{font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#222;margin:0;padding:16px;}
p{margin:0 0 0.8em;}
h1,h2,h3,h4{margin:0.8em 0 0.4em;font-weight:bold;}
h1{font-size:1.3em;}h2{font-size:1.15em;}h3{font-size:1.05em;}
ul,ol{margin:0 0 0.8em;padding-left:1.6em;}
li{margin-bottom:0.2em;}
table{border-collapse:collapse;width:100%;margin:0 0 0.8em;}
th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;}
th{background:#f5f5f5;font-weight:bold;}
blockquote{margin:0 0 0.8em;padding:0.4em 0.8em;border-left:3px solid #aaa;color:#555;}
code{background:#f4f4f4;padding:0.1em 0.3em;border-radius:3px;font-family:monospace;font-size:0.9em;}
pre{background:#f4f4f4;padding:0.8em;border-radius:4px;overflow-x:auto;white-space:pre-wrap;font-family:Consolas,Monaco,monospace;font-size:0.85em;}
hr{border:none;border-top:1px solid #ddd;margin:1em 0;}
a{color:#1a73e8;}
.page-break{page-break-before:always;break-before:page;}
""".strip()


@dataclass
class RenderResult:
    html: str
    plain: str


_FENCE_RE = re.compile(r'```.*?```', re.DOTALL)

_MATH_MACRO_MAP = {
    'ge': '≥', 'geq': '≥',
    'le': '≤', 'leq': '≤',
    'ne': '≠', 'neq': '≠',
    'pm': '±',
    'times': '×',
    'div': '÷',
    'approx': '≈',
    'cdot': '·',
    'infty': '∞',
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'mu': 'μ', 'sigma': 'σ',
}
_MATH_MACRO_RE = re.compile(r'\\(' + '|'.join(_MATH_MACRO_MAP) + r')\b')
# Trigger on a backslash command (\ge, \alpha, ...) OR a bare </> comparison —
# unlike a hyphen (a genuine currency-range separator, e.g. "$50-$100"), a
# literal < or > right next to a dollar amount has no plausible currency
# meaning, so it's safe to add without risking a false positive there.
_MATH_SPAN_RE = re.compile(r'\$([^$\n]*(?:\\[a-zA-Z]+|[<>])[^$\n]*)\$')


def _normalize_math(text: str) -> str:
    """Convert simple inline LaTeX math (e.g. '$\\ge 1$') to plain Unicode
    text ('≥ 1'). Models trained heavily on scientific/clinical literature
    default to LaTeX notation for thresholds and comparisons — especially in
    exactly the kind of structured diagnostic-criteria tables this renderer
    handles — but nothing downstream (Markdown, the sanitizer, the Rendered
    tab's sandboxed iframe with no allow-scripts) understands LaTeX, so it
    was passing straight through as literal '$\\ge 1$' source text.

    Only a '$...$' span containing a backslash command is touched — a plain
    dollar amount ('$50 to $200') never has a backslash inside it, so this
    can't misfire on ordinary currency text that happens to put two '$'
    signs on one line."""
    def _convert(match: re.Match) -> str:
        inner = _MATH_MACRO_RE.sub(lambda m: _MATH_MACRO_MAP[m.group(1)], match.group(1))
        return inner.strip()
    return _MATH_SPAN_RE.sub(_convert, text)


def _looks_like_html(text: str) -> bool:
    """True only when the source itself IS HTML (e.g. pasted from an email
    client) — not when it's Markdown that merely contains a fenced code
    sample, or embeds a raw HTML block (CommonMark/Markdown both allow this
    while still converting everything else). Content inside fenced code
    blocks is stripped first, and the remainder must *start* with an HTML
    tag — matching anywhere would misclassify a Markdown document that just
    happens to embed one raw <div> (e.g. a print page-break marker)."""
    stripped = _FENCE_RE.sub('', text).strip()
    return bool(re.match(r'<(!DOCTYPE|html|body|p|div|br|h[1-6]|ul|ol|table)\b', stripped, re.IGNORECASE))


_HTML_FENCE_RE = re.compile(r'```(\w*)\n([\s\S]*?)```')


def _extract_full_html_doc(text: str) -> str | None:
    """Server-side mirror of the client-side extractHtmlDoc() used by the
    chatbot/library Rendered tabs and Open button (chatbot_panel.html,
    doc_library/editor.html) — detects a fenced or bare block that is a
    *complete* HTML document, as opposed to a small HTML snippet or tag
    mentioned elsewhere in otherwise-Markdown content. Kept in sync with
    that JS implementation; same fence-body / bare-document criteria."""
    if not text:
        return None
    for m in _HTML_FENCE_RE.finditer(text):
        body = m.group(2).strip()
        if re.match(r'<!DOCTYPE html', body, re.IGNORECASE) or re.match(r'<html[\s>]', body, re.IGNORECASE):
            return body
    m = (re.search(r'<!DOCTYPE html[\s\S]*</html>', text, re.IGNORECASE) or
         re.search(r'<html[\s>][\s\S]*</html>', text, re.IGNORECASE))
    return m.group(0) if m else None


# A line with 2+ runs of "multiple spaces" or a tab is a strong signal of a
# space/tab-padded plain-text table row (e.g. pasted from a pathology report
# rollup) — ordinary prose rarely has more than one incidental double-space.
# A single such run is a weaker signal (also matches a table's own header/
# title row, e.g. "Date   17-Feb-26 23-Feb-26 ..." only has one wide gap
# before the single-spaced date tokens) — only trusted when adjacent to a
# strong row, so it doesn't get flagged in isolation from ordinary prose.
_COLUMN_GAP_RE = re.compile(r'(?:  +|\t)')


def _is_markdown_table_line(line: str) -> bool:
    """True for a genuine GFM table row/separator (`| a | b |`, `|---|---|`)
    — these must be left alone so Markdown's own `tables` extension renders
    them, not swept into a plain-text columnar block by the padding they
    often carry for source readability."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith('|') and stripped.endswith('|'):
        return True
    return bool(re.fullmatch(r'[-|: ]+', stripped) and '-' in stripped)


_EXISTING_FENCE_RE = re.compile(r'(^```.*?\n[\s\S]*?^```[ \t]*$)', re.MULTILINE)


def _protect_columnar_blocks(source: str) -> str:
    """Wrap runs of space/tab-aligned plain-text lines in fenced code blocks
    so Markdown (and the browser/email client rendering the result) preserve
    their alignment instead of collapsing it like ordinary paragraph text.

    Content already inside a fenced code block in the *source* is left
    completely untouched and never re-scanned: applying the same line-by-line
    heuristic inside an already-fenced block would inject a second, nested
    pair of ``` markers around its columnar interior, throwing off Markdown's
    fence parity so only part of the original block ends up inside <pre> and
    the rest falls through as ordinary text (where HTML collapses the very
    spacing this function exists to protect)."""
    parts = _EXISTING_FENCE_RE.split(source)
    return ''.join(
        part if part.startswith('```') else _protect_columnar_lines(part)
        for part in parts
    )


def _protect_columnar_lines(source: str) -> str:
    lines = source.split('\n')
    is_md_table = [_is_markdown_table_line(line) for line in lines]
    gap_counts = [len(_COLUMN_GAP_RE.findall(line)) for line in lines]
    strong = [c >= 2 and not is_md_table[i] for i, c in enumerate(gap_counts)]
    weak   = [c >= 1 and not is_md_table[i] for i, c in enumerate(gap_counts)]

    include = list(strong)

    # Flood-fill: a weak-signal or blank line joins the block if it's
    # touching a line already in it — pulls in a table's header/title rows
    # and internal blank spacer rows without touching genuine prose. A real
    # markdown table row/separator is never absorbed, even if adjacent.
    changed = True
    while changed:
        changed = False
        for i, line in enumerate(lines):
            if include[i] or is_md_table[i]:
                continue
            neighbour_included = (
                (i > 0 and include[i - 1]) or (i < len(lines) - 1 and include[i + 1])
            )
            if neighbour_included and (weak[i] or not line.strip()):
                include[i] = True
                changed = True

    out: list[str] = []
    i = 0
    while i < len(lines):
        if include[i]:
            j = i
            while j < len(lines) and include[j]:
                j += 1
            block = '\n'.join(lines[i:j]).strip('\n')
            out.append('```\n' + block + '\n```')
            i = j
        else:
            out.append(lines[i])
            i += 1
    return '\n'.join(out)


def _md_to_html(source: str) -> str:
    return _md.markdown(
        _protect_columnar_blocks(source),
        extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists'],
    )


def _sanitize(html: str) -> str:
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def _inline_css(html: str) -> str:
    """Wrap in a minimal email-ready document and inline CSS."""
    full = (
        f'<html><head><style>{_EMAIL_CSS}</style></head>'
        f'<body>{html}</body></html>'
    )
    try:
        import css_inline
        inliner = css_inline.CSSInliner(keep_style_tags=False)
        return inliner.inline(full)
    except Exception:
        return full


def _html_to_plain(html: str) -> str:
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|h[1-6]|li|tr)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    import html as _html_lib
    text = _html_lib.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def render(source: str) -> RenderResult:
    """Convert source text to sanitized HTML + plain-text pair."""
    if not source:
        return RenderResult(html='', plain='')

    source = _normalize_math(source)

    full_doc = _extract_full_html_doc(source)
    if full_doc is not None:
        # A complete, self-contained HTML document (e.g. AI-generated reference
        # material) is returned as-is rather than run through the sanitizer or
        # Markdown converter — bleach's restrictive tag allowlist has no
        # <html>/<head>/<style>, so it would strip those and leave the page's
        # own CSS dumped as literal text; the fenced_code Markdown extension
        # would escape the whole thing into a visible <pre><code> block. This
        # matches how the client-side Rendered tab / Open button already treat
        # this exact content class (chatbot_panel.html, doc_library/editor.html
        # extractHtmlDoc()) — sent/rendered untouched rather than mangled.
        return RenderResult(html=full_doc, plain=_html_to_plain(full_doc))

    if _looks_like_html(source):
        sanitized = _sanitize(source)
    else:
        raw_html = _md_to_html(source)
        sanitized = _sanitize(raw_html)

    inlined = _inline_css(sanitized)
    plain = _html_to_plain(sanitized)

    return RenderResult(html=inlined, plain=plain)
