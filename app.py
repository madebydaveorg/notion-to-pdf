"""
Notion → PDF Web App
Flask server that converts public Notion pages to downloadable PDFs.
"""

import os
import io
import re
import logging
from flask import Flask, request, jsonify, send_file, render_template
from converter import convert, to_text, extract_page_id

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Simple in-memory rate limiting (per IP, 20 requests/min)
from collections import defaultdict
import time

_rate = defaultdict(list)
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 20))
RATE_WINDOW = 60  # seconds


def _check_rate(ip: str) -> bool:
    now = time.time()
    _rate[ip] = [t for t in _rate[ip] if now - t < RATE_WINDOW]
    if len(_rate[ip]) >= RATE_LIMIT:
        return False
    _rate[ip].append(now)
    return True


def _is_notion_url(url: str) -> bool:
    """Basic validation that this looks like a Notion URL."""
    url = url.strip().lower()
    if re.search(r"[a-f0-9]{32}", url):
        return True
    if "notion.so" in url or "notion.site" in url:
        return True
    return False


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/convert", methods=["POST"])
def api_convert():
    ip = request.remote_addr or "unknown"
    if not _check_rate(ip):
        return jsonify({"error": "Rate limit exceeded. Please wait a minute."}), 429

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "Please provide a Notion page URL."}), 400
    if not _is_notion_url(url):
        return jsonify({"error": "That doesn't look like a valid Notion URL."}), 400

    fmt = data.get("format", "pdf")  # "pdf" or "text"

    try:
        if fmt == "text":
            text, title = to_text(url)
            return jsonify({"title": title, "text": text})
        else:
            pdf_bytes, title = convert(url)
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:60]
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"{slug}.pdf",
            )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("Conversion failed")
        return jsonify({"error": f"Conversion failed: {str(e)}"}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
