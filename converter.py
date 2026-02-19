"""
Notion Page → PDF/Text converter engine.
Fetches public Notion pages via their internal API,
renders to styled HTML, and converts to PDF with WeasyPrint.
"""

import re
import html as html_module
import requests
from pathlib import Path


# ── URL / ID helpers ─────────────────────────────────────────────────────────

def extract_page_id(url: str) -> str:
    """Extract and format a Notion page UUID from various URL formats."""
    url = url.strip().rstrip("/")
    for pat in [
        r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
        r"([a-f0-9]{32})",
    ]:
        m = re.search(pat, url)
        if m:
            raw = m.group(1).replace("-", "")
            return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    raise ValueError(f"Could not extract a Notion page ID from: {url}")


def slug_from_url(url: str) -> str:
    path = url.split("?")[0].rstrip("/").split("/")[-1]
    name = re.sub(r"-?[a-f0-9]{32}$", "", path)
    return name.replace("-", "_").strip("_") or "notion_page"


# ── Notion API fetcher ───────────────────────────────────────────────────────

class NotionFetcher:
    BASE = "https://www.notion.so/api/v3"
    HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, page_id: str):
        self.page_id = page_id
        self.blocks: dict = {}

    def fetch(self) -> dict:
        chunk, cursor = 0, {"stack": []}
        while True:
            resp = requests.post(
                f"{self.BASE}/loadPageChunk",
                json={
                    "page": {"id": self.page_id},
                    "limit": 100,
                    "cursor": cursor,
                    "chunkNumber": chunk,
                    "verticalColumns": False,
                },
                headers=self.HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            self.blocks.update(data.get("recordMap", {}).get("block", {}))
            new_cursor = data.get("cursor", {})
            if not new_cursor.get("stack") or chunk > 20:
                break
            cursor, chunk = new_cursor, chunk + 1
        return self.blocks


# ── Block → HTML renderer ───────────────────────────────────────────────────

class NotionRenderer:
    def __init__(self, blocks: dict):
        self.blocks = blocks

    # -- public --
    def render_page(self) -> tuple[str, str]:
        """Returns (html_string, page_title)."""
        root_id, title, icon, cover = None, "Notion Page", "", ""

        for bid, bd in self.blocks.items():
            v = bd.get("value", {})
            if v.get("type") == "page":
                root_id = root_id or bid
                t = self._plain(v.get("properties", {}).get("title", []))
                if t:
                    title, icon, cover = (
                        t,
                        v.get("format", {}).get("page_icon", ""),
                        v.get("format", {}).get("page_cover", ""),
                    )

        body = ""
        if root_id:
            children = self.blocks[root_id].get("value", {}).get("content", [])
            body = self._render_ids(children)

        html = self._document(title, icon, cover, body)
        html = re.sub(r"</ul>\s*<ul>", "", html)
        html = re.sub(r"</ol>\s*<ol>", "", html)
        return html, title

    # -- recursive block render --
    def _render_ids(self, ids: list, depth: int = 0) -> str:
        return "\n".join(
            r
            for bid in ids
            if (r := self._render(self.blocks.get(bid, {}).get("value", {}), depth))
        )

    def _render(self, b: dict, depth: int = 0) -> str:
        if not b:
            return ""
        tp = b.get("type", "")
        pr = b.get("properties", {})
        fm = b.get("format", {})
        tx = self._rich(pr.get("title", []))
        ch = b.get("content", [])
        ch_html = self._render_ids(ch, depth + 1) if ch else ""

        match tp:
            case "page":
                return f'<div class="sub-page">📄 {html_module.escape(self._plain(pr.get("title", [])))}</div>'
            case "header":
                return f"<h1>{tx}</h1>"
            case "sub_header":
                return f"<h2>{tx}</h2>"
            case "sub_sub_header":
                return f"<h3>{tx}</h3>"
            case "text":
                return f"<p>{tx}</p>" if tx.strip() else "<br/>"
            case "bulleted_list":
                inner = f"<li>{tx}{'<ul>' + ch_html + '</ul>' if ch_html else ''}</li>"
                return f"<ul>{inner}</ul>"
            case "numbered_list":
                inner = f"<li>{tx}{'<ol>' + ch_html + '</ol>' if ch_html else ''}</li>"
                return f"<ol>{inner}</ol>"
            case "to_do":
                ck = pr.get("checked", [["No"]])[0][0]
                return f'<p class="todo">{"☑" if ck == "Yes" else "☐"} {tx}</p>'
            case "toggle":
                return f"<details><summary>{tx}</summary><div>{ch_html}</div></details>"
            case "quote":
                return f"<blockquote>{tx}</blockquote>"
            case "callout":
                ic = fm.get("page_icon", "💡")
                return f'<div class="callout"><span class="ci">{ic}</span><div>{tx}{ch_html}</div></div>'
            case "divider":
                return "<hr/>"
            case "code":
                return f"<pre><code>{html_module.escape(self._plain(pr.get('title', [])))}</code></pre>"
            case "image":
                src = fm.get("display_source") or self._plain(pr.get("source", []))
                if src:
                    if src.startswith("/"):
                        src = "https://www.notion.so" + src
                    cap = self._plain(pr.get("caption", []))
                    cap_h = f"<figcaption>{html_module.escape(cap)}</figcaption>" if cap else ""
                    return f'<figure><img src="{src}" alt=""/>{cap_h}</figure>'
            case "bookmark":
                lk = pr.get("link", [["#"]])[0][0] if pr.get("link") else "#"
                lt = self._plain(pr.get("title", [])) or lk
                return f'<div class="bookmark"><a href="{html_module.escape(lk)}">{html_module.escape(lt)}</a></div>'
            case "equation":
                return f'<div class="equation">{html_module.escape(self._plain(pr.get("title", [])))}</div>'
            case "column_list" | "column":
                return ch_html
            case "table":
                return f"<table>{ch_html}</table>"
            case "table_row":
                cells = "".join(f"<td>{self._rich(v)}</td>" for _, v in sorted(pr.items()))
                return f"<tr>{cells}</tr>" if cells else ""
            case "video" | "embed" | "pdf":
                src = self._plain(pr.get("source", []))
                if src:
                    return f'<div class="media-embed"><a href="{html_module.escape(src)}">🔗 {html_module.escape(src)}</a></div>'

        return f"<div>{ch_html}</div>" if ch_html else ""

    # -- text helpers --
    def _plain(self, arr: list) -> str:
        if not arr:
            return ""
        return "".join(str(c[0]) for c in arr if isinstance(c, list) and c)

    def _rich(self, arr: list) -> str:
        if not arr:
            return ""
        parts = []
        for chunk in arr:
            if not isinstance(chunk, list) or not chunk:
                continue
            t = html_module.escape(str(chunk[0]))
            if len(chunk) > 1 and isinstance(chunk[1], list):
                for f in chunk[1]:
                    if not isinstance(f, list) or not f:
                        continue
                    match f[0]:
                        case "b":
                            t = f"<strong>{t}</strong>"
                        case "i":
                            t = f"<em>{t}</em>"
                        case "s":
                            t = f"<s>{t}</s>"
                        case "c":
                            t = f"<code>{t}</code>"
                        case "_":
                            t = f"<u>{t}</u>"
                        case "a" if len(f) > 1:
                            t = f'<a href="{html_module.escape(str(f[1]))}">{t}</a>'
                        case "h" if len(f) > 1:
                            t = f'<span class="color-{f[1]}">{t}</span>'
            parts.append(t)
        return "".join(parts)

    # -- full HTML document --
    def _document(self, title: str, icon: str, cover: str, body: str) -> str:
        icon_h = (
            f'<div class="page-icon">{icon}</div>'
            if icon and not icon.startswith("http")
            else ""
        )
        cover_h = ""
        if cover:
            if cover.startswith("/"):
                cover = "https://www.notion.so" + cover
            cover_h = f'<div class="page-cover"><img src="{cover}"/></div>'

        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<title>{html_module.escape(title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:15px;line-height:1.7;color:#37352f;max-width:750px;margin:0 auto;padding:40px 30px}}
.page-cover img{{width:100%;max-height:200px;object-fit:cover;border-radius:4px;margin-bottom:20px}}
.page-icon{{font-size:50px;margin-bottom:10px}}
.page-title{{font-size:32px;font-weight:700;margin-bottom:8px;line-height:1.2}}
h1{{font-size:24px;font-weight:600;margin:28px 0 8px;padding-top:12px}}
h2{{font-size:20px;font-weight:600;margin:22px 0 6px}}
h3{{font-size:17px;font-weight:600;margin:18px 0 4px}}
p{{margin:4px 0}}a{{color:#2f81f7;text-decoration:underline}}
ul,ol{{margin:2px 0 2px 24px}}li{{margin:2px 0}}
code{{font-family:'SFMono-Regular',Consolas,monospace;font-size:13px;background:#f7f6f3;padding:2px 5px;border-radius:3px}}
pre{{background:#f7f6f3;border-radius:6px;padding:16px 20px;margin:10px 0;overflow-x:auto;border:1px solid #e3e2e0}}
pre code{{background:none;padding:0;font-size:13px;line-height:1.5}}
blockquote{{border-left:3px solid #37352f;padding:4px 16px;margin:10px 0}}
.callout{{display:flex;gap:10px;padding:16px;border-radius:6px;margin:10px 0;background:#f1f1ef}}
.ci{{font-size:20px;flex-shrink:0}}
hr{{border:none;border-top:1px solid #e3e2e0;margin:16px 0}}
figure{{margin:14px 0;text-align:center}}figure img{{max-width:100%;border-radius:4px}}
figcaption{{font-size:13px;color:#787774;margin-top:6px}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}}
td,th{{border:1px solid #e3e2e0;padding:8px 12px;text-align:left}}
tr:first-child td{{font-weight:600;background:#f7f6f3}}
.sub-page{{padding:8px 12px;border:1px solid #e3e2e0;border-radius:4px;margin:4px 0;font-weight:500}}
.bookmark{{border:1px solid #e3e2e0;border-radius:6px;padding:12px 16px;margin:8px 0}}
.media-embed{{padding:12px;background:#f7f6f3;border-radius:6px;margin:8px 0}}
.equation{{text-align:center;font-family:monospace;font-size:16px;padding:10px;margin:8px 0}}
.todo{{margin:3px 0}}details{{margin:6px 0}}summary{{cursor:pointer;font-weight:500}}
.color-gray{{color:#787774}}.color-brown{{color:#9f6b53}}.color-orange{{color:#d9730d}}
.color-yellow{{color:#cb912f}}.color-green{{color:#448361}}.color-blue{{color:#337ea9}}
.color-purple{{color:#9065b0}}.color-pink{{color:#c14c8a}}.color-red{{color:#d44c47}}
@media print{{body{{padding:0}}pre{{white-space:pre-wrap;word-wrap:break-word}}}}
</style></head><body>
{cover_h}{icon_h}
<h1 class="page-title">{html_module.escape(title)}</h1>
<div class="page-content">{body}</div>
</body></html>"""


# ── Plain-text extraction (for AI reading) ───────────────────────────────────

def _walk_text(blocks: dict, ids: list, lines: list, depth: int):
    for bid in ids:
        v = blocks.get(bid, {}).get("value", {})
        if not v:
            continue
        tp = v.get("type", "")
        pr = v.get("properties", {})
        arr = pr.get("title", [])
        tx = "".join(str(c[0]) for c in arr if isinstance(c, list) and c)
        ind = "  " * depth
        match tp:
            case "header":
                lines.append(f"\n## {tx}")
            case "sub_header":
                lines.append(f"\n### {tx}")
            case "sub_sub_header":
                lines.append(f"\n#### {tx}")
            case "text" if tx.strip():
                lines.append(f"{ind}{tx}")
            case "bulleted_list" | "numbered_list":
                lines.append(f"{ind}• {tx}")
            case "to_do":
                ck = pr.get("checked", [["No"]])[0][0]
                lines.append(f'{ind}[{"x" if ck == "Yes" else " "}] {tx}')
            case "quote":
                lines.append(f"{ind}> {tx}")
            case "code":
                lines.append(f"{ind}```\n{ind}{tx}\n{ind}```")
            case "callout":
                ic = v.get("format", {}).get("page_icon", "")
                lines.append(f"{ind}{ic} {tx}")
            case "divider":
                lines.append("---")
        ch = v.get("content", [])
        if ch:
            _walk_text(blocks, ch, lines, depth + 1)


# ── Public API ───────────────────────────────────────────────────────────────

def convert(url: str) -> tuple[bytes, str]:
    """
    Convert a public Notion page → PDF bytes.
    Returns (pdf_bytes, page_title).
    """
    page_id = extract_page_id(url)
    fetcher = NotionFetcher(page_id)
    blocks = fetcher.fetch()
    renderer = NotionRenderer(blocks)
    html_str, title = renderer.render_page()

    from weasyprint import HTML

    pdf_bytes = HTML(string=html_str, base_url="https://www.notion.so").write_pdf()
    return pdf_bytes, title


def to_text(url: str) -> tuple[str, str]:
    """
    Extract plain text from a public Notion page.
    Returns (text, page_title).
    """
    page_id = extract_page_id(url)
    fetcher = NotionFetcher(page_id)
    blocks = fetcher.fetch()
    root_id, title = None, "Notion Page"
    for bid, bd in blocks.items():
        v = bd.get("value", {})
        if v.get("type") == "page":
            root_id = root_id or bid
            t = "".join(
                str(c[0])
                for c in v.get("properties", {}).get("title", [])
                if isinstance(c, list) and c
            )
            if t:
                title = t
    lines = [f"# {title}\n"]
    if root_id:
        _walk_text(blocks, blocks[root_id].get("value", {}).get("content", []), lines, 0)
    return "\n".join(lines), title
