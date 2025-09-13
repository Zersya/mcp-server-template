# MCP Server Template

A minimal [FastMCP](https://github.com/jlowin/fastmcp) server template for Render deployment with streamable HTTP transport.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/InteractionCo/mcp-server-template)

## Local Development

### Setup

Fork the repo, then run:

```bash
git clone <your-repo-url>
cd mcp-server-template
conda create -n mcp-server python=3.13
conda activate mcp-server
pip install -r requirements.txt
```

### Test

```bash
python src/server.py
# then in another terminal run:
npx @modelcontextprotocol/inspector
```

Open http://localhost:3000 and connect to `http://localhost:8000/mcp` using "Streamable HTTP" transport (NOTE THE `/mcp`!).

## Deployment

### Option 1: One-Click Deploy
Click the "Deploy to Render" button above.

### Option 2: Manual Deployment
1. Fork this repository
2. Connect your GitHub account to Render
3. Create a new Web Service on Render
4. Connect your forked repository
5. Render will automatically detect the `render.yaml` configuration

Your server will be available at `https://your-service-name.onrender.com/mcp` (NOTE THE `/mcp`!)

## Customization

## Social Media & Image Toolkit

This server includes MCP tools for Instagram scraping, image fetching, and AI-powered image editing.

### Instagram Scraping (Apify)
Uses Apify's `instagram-scraper` to collect Instagram content.

### Image Fetching (Unsplash)
Search and download free-to-use images from Unsplash's extensive collection.

### Image Editing (Replicate AI)
Edit images using AI models via Replicate's `google/nano-banana` model.

### Cloud Storage (Cloudflare R2)
Automatically upload all images to Cloudflare R2 storage with public URLs and time-limited access.

## Environment Variables

**Required:**
- `APIFY_TOKEN`: Apify API token for Instagram scraping
- `UNSPLASH_ACCESS_KEY`: Unsplash API access key for image fetching
- `REPLICATE_API_TOKEN`: Replicate API token for image editing

**Cloudflare R2 Storage (Optional but Recommended):**
- `CLOUDFLARE_R2_ACCOUNT_ID`: Cloudflare account ID
- `CLOUDFLARE_R2_ACCESS_KEY_ID`: R2 access key
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`: R2 secret key
- `CLOUDFLARE_R2_BUCKET_NAME`: Target bucket name
- `CLOUDFLARE_R2_PUBLIC_DOMAIN`: Custom domain for public URLs (optional)

**Notifications:**
- `POKE_API_KEY`: API key for SMS notifications (includes image URLs when R2 is configured)
- `NOTIFY_URL`: Webhook URL for notifications (defaults to `https://poke.com/api/v1/inbound-sms/webhook`)

## MCP Tools

### Instagram Scraping
- `instagram_scrape(usernames?: string[], hashtags?: string[], search?: string, results_limit?: number=50, proxy_country?: string)`

### Image Operations
- `image_fetch_unsplash(query: string, count?: number=5, orientation?: string, color?: string, download_images?: boolean=true)`
- `image_edit_replicate(image_input: string, prompt: string, additional_images?: string[], save_locally?: boolean=true)`

## Features

- **Instagram Scraping**: Collect posts, profiles, and hashtag content
- **Image Search**: Find free-to-use images with proper attribution
- **AI Image Editing**: Modify images using natural language prompts
- **Cloud Storage**: Automatic upload to Cloudflare R2 with organized folders (`/fetched/`, `/edited/`)
- **Public URLs**: Time-limited access URLs (24 hours) for easy sharing
- **SMS Notifications**: Status updates with image URLs sent after each operation
- **Local Backup**: Downloaded images saved to `./images/` directory as backup
- **Integration**: Tools work together - edit Instagram images or Unsplash photos
- **Error Handling**: Graceful degradation when cloud storage is unavailable

## Cloud Storage Structure

When Cloudflare R2 is configured, images are automatically organized in folders:
- `/fetched/` - Images downloaded from Unsplash
- `/edited/` - AI-edited images from Replicate

Each image gets:
- **R2 URL**: `s3://bucket-name/folder/filename.jpg`
- **Public URL**: Time-limited access URL (24 hours)
- **Expiration**: Automatic cleanup after expiration period

## SMS Notifications

When both R2 storage and SMS notifications are configured:
- Receive instant notifications with public image URLs
- URLs are included in SMS messages with expiration info
- Format: `"Operation completed - Images: [URL] - expires in 24h"`

Setup dependencies:
```bash
pip install -r requirements.txt
```

Run locally:
```bash
python src/server.py
# In another terminal
npx @modelcontextprotocol/inspector
```


Add more tools by decorating functions with `@mcp.tool`:

```python
@mcp.tool
def calculate(x: float, y: float, operation: str) -> float:
    """Perform basic arithmetic operations."""
    if operation == "add":
        return x + y
    elif operation == "multiply":
        return x * y
    # ...
```
