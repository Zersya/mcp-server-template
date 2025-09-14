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
Uses Apify's `instagram-scraper` to collect Instagram content from usernames, profile URLs, or specific post URLs. Plain usernames are automatically converted to Instagram profile URLs.

### Image Fetching (Unsplash)
Search and download free-to-use images from Unsplash's extensive collection.

### Image Editing (Replicate AI)
Edit images using AI models via Replicate's `google/nano-banana` model.

### Cloud Storage (Cloudflare R2)
Automatically upload all images to Cloudflare R2 storage with public URLs and time-limited access.

### Instagram Posting (Late.dev)
Schedule and publish Instagram posts using the Late.dev API with images from Unsplash, AI-edited images, or external URLs.

## Workflow Examples

### Complete Instagram Content Pipeline
1. **Fetch Images**: Use `image_fetch_unsplash()` to download royalty-free images
2. **Edit Images**: Use `image_edit_replicate()` to enhance images with AI
3. **Post to Instagram**: Use `instagram_post_schedule()` with R2 URLs from previous steps
4. **Get Notifications**: Receive SMS notifications with post URLs and image links

### Instagram Research & Posting
1. **Research Content**: Use `instagram_scrape()` to analyze competitor posts
2. **Create Content**: Use `image_fetch_unsplash()` and `image_edit_replicate()` for visuals
3. **Schedule Posts**: Use `instagram_post_schedule()` to publish at optimal times

## Usage Examples

### Instagram Scraping with Username Conversion
```python
# Plain usernames (automatically converted to URLs)
instagram_scrape(
    username=["kugie.app", "natgeo", "@nasa"],  # @ symbol is automatically removed
    results_limit=30
)
# Converts to: ["https://www.instagram.com/kugie.app/", "https://www.instagram.com/natgeo/", "https://www.instagram.com/nasa/"]

# Mixed input types
instagram_scrape(
    username=[
        "kugie.app",  # Plain username -> converted to URL
        "https://www.instagram.com/natgeo/",  # Profile URL -> kept as is
        "https://www.instagram.com/p/ABC123/"  # Post URL -> kept as is
    ],
    results_limit=50
)
```

## Environment Variables

**Required:**
- `APIFY_TOKEN`: Apify API token for Instagram scraping
- `UNSPLASH_ACCESS_KEY`: Unsplash API access key for image fetching
- `REPLICATE_API_TOKEN`: Replicate API token for image editing
- `LATE_DEV_API_KEY`: Late.dev API key for Instagram posting

**Cloudflare R2 Storage (Optional but Recommended):**
- `CLOUDFLARE_R2_ACCOUNT_ID`: Cloudflare account ID
- `CLOUDFLARE_R2_ACCESS_KEY_ID`: R2 access key
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`: R2 secret key
- `CLOUDFLARE_R2_BUCKET_NAME`: Target bucket name
- `CLOUDFLARE_R2_PUBLIC_DOMAIN`: Custom domain for public URLs (optional)
- `CLOUDFLARE_R2_PUBLIC_SUBDOMAIN`: R2 public subdomain (e.g., "pub-4c735be9ea544be589c605db1cbddec0") (optional)

**Notifications:**
- `POKE_API_KEY`: API key for SMS notifications (includes image URLs when R2 is configured)
- `NOTIFY_URL`: Webhook URL for notifications (defaults to `https://poke.com/api/v1/inbound-sms/webhook`)

## MCP Tools

### Instagram Scraping
- `instagram_scrape(direct_urls?: string[], results_limit?: number=200, results_type?: string="posts", add_parent_data?: boolean=false, enhance_user_search_with_facebook_page?: boolean=false, is_user_reel_feed_url?: boolean=false, is_user_tagged_feed_url?: boolean=false, search_type?: string, search_query?: string, search_limit?: number=1, proxy_country?: string)`

Example matching Apify input:
```json
{
  "addParentData": false,
  "directUrls": [
    "https://www.instagram.com/kugie.app/"
  ],
  "enhanceUserSearchWithFacebookPage": false,
  "isUserReelFeedURL": false,
  "isUserTaggedFeedURL": false,
  "resultsLimit": 200,
  "resultsType": "posts",
  "searchLimit": 1,
  "searchType": "hashtag"
}
```
Notes:
- You can pass plain usernames in `direct_urls` (e.g., "kugie.app" or "@kugie.app"); they will be converted to `https://www.instagram.com/<username>/` automatically.
- For searches, provide both `search_type` (e.g., "hashtag") and `search_query` (e.g., "sunset").

### Image Operations
- `image_fetch_unsplash(query: string, count?: number=5, orientation?: string, color?: string, download_images?: boolean=true)`
- `image_edit_replicate(image_input: string, prompt: string, additional_images?: string[], save_locally?: boolean=true)`

### Instagram Posting
- `instagram_post_schedule(content: string, image_source: string, instagram_account_id: string, schedule_time?: string, timezone?: string="UTC", publish_now?: boolean=false, content_type?: string="post", collaborators?: string[])`

### Cloud Storage Setup
- `cloudflare_r2_public_setup()`: Configure R2 bucket for public access and troubleshoot URL authorization errors

### Cloud Storage Troubleshooting
- `r2_troubleshoot_access()`: Diagnose and fix R2 public access issues, including "InvalidArgument Authorization" errors

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

## Troubleshooting R2 Access Issues

### "InvalidArgument Authorization" Error
If you get this error when accessing image URLs via WhatsApp or other apps:

1. **Use the troubleshooting tool:**
   ```
   Call r2_troubleshoot_access() to diagnose the issue
   ```

2. **Quick fix:** Enable public access on your R2 bucket:
   - Go to Cloudflare Dashboard → R2 → Your Bucket → Settings
   - Enable "Allow Access" under Public URL Access

3. **Best solution:** Set up a custom domain for reliable public access:
   - Go to Cloudflare Dashboard → R2 → Your Bucket
   - Click "Connect Domain" and configure a custom domain
   - Set `CLOUDFLARE_R2_PUBLIC_DOMAIN` environment variable

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
