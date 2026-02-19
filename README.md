# Notion → PDF

A web app that converts any public Notion page into a clean, downloadable PDF. Also extracts plain text for AI/LLM analysis.

## What it does

- Paste any public Notion page URL
- Get a beautifully formatted PDF (styled to match Notion's look)
- Or extract clean markdown-style plain text
- Supports all major block types: headings, lists, code, callouts, quotes, tables, toggles, images, bookmarks, and more

## Project structure

```
notion-to-pdf-app/
├── app.py              # Flask web server
├── converter.py        # Notion API → HTML → PDF engine
├── templates/
│   └── index.html      # Frontend UI
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container build
├── railway.toml        # Railway config
├── render.yaml         # Render config
├── fly.toml            # Fly.io config
└── README.md
```

## Deploy in under 5 minutes

Pick whichever platform you prefer. All three have free tiers.

---

### Option 1: Railway (recommended — easiest)

1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the repo — Railway auto-detects the Dockerfile
4. Click **Deploy** — done. Railway gives you a `*.up.railway.app` URL
5. To add your own domain: Settings → Networking → Custom Domain

**Cost:** Free tier gives you $5/month of usage (~500 conversions/month). Starter plan is $5/month.

---

### Option 2: Render

1. Push to GitHub
2. Go to [render.com](https://render.com) → New → Web Service → Connect your repo
3. Select **Docker** as the runtime
4. Click **Create Web Service**
5. Custom domain: Settings → Custom Domains

**Cost:** Free tier available (spins down after inactivity, ~30s cold start). Starter is $7/month.

---

### Option 3: Fly.io

1. Install the Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Sign up: `fly auth signup`
3. From the project folder:

```bash
fly launch          # creates the app (accept defaults)
fly deploy          # builds + deploys
fly domains add yourdomain.com   # optional: custom domain
```

**Cost:** Free tier includes 3 shared VMs. Pay-as-you-go after that.

---

### Option 4: Any VPS (DigitalOcean, etc.)

```bash
# On your server
git clone <your-repo-url>
cd notion-to-pdf-app
docker build -t notion-pdf .
docker run -d -p 80:8080 --restart=unless-stopped notion-pdf
```

Then point your domain's A record to the server IP.

---

## Run locally

```bash
# Install system deps (macOS)
brew install pango libffi

# Install system deps (Ubuntu/Debian)
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libcairo2

# Install Python deps
pip install -r requirements.txt

# Run
python app.py
# → http://localhost:8080
```

## Custom domain setup

Whichever platform you deploy to, connecting a custom domain is the same idea:

1. In your platform's dashboard, add your domain (e.g., `pdf.yourdomain.com`)
2. The platform gives you a CNAME target (e.g., `xxx.up.railway.app`)
3. In your DNS provider (Squarespace, Cloudflare, etc.), add:
   - **Type:** CNAME
   - **Host:** `pdf` (or whatever subdomain)
   - **Value:** the target from step 2
4. Wait for DNS propagation (usually < 5 min)
5. HTTPS is automatic on all three platforms

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Server port |
| `RATE_LIMIT` | `20` | Max requests per IP per minute |
| `FLASK_DEBUG` | `0` | Set to `1` for dev mode |

## API

The app also works as an API if you want to integrate it elsewhere:

```bash
# Get PDF
curl -X POST https://yourdomain.com/api/convert \
  -H "Content-Type: application/json" \
  -d '{"url": "https://acme.notion.site/Page-abc123", "format": "pdf"}' \
  --output page.pdf

# Get plain text
curl -X POST https://yourdomain.com/api/convert \
  -H "Content-Type: application/json" \
  -d '{"url": "https://acme.notion.site/Page-abc123", "format": "text"}'
```

## Limitations

- **Public pages only** — the Notion page must have "Share to web" enabled
- **No authentication** — can't access private/workspace pages
- **Images** — Notion-hosted images may not render if they require auth tokens
- **Databases** — collection/database views are partially supported (basic table rows work, filtered/sorted views may not)
