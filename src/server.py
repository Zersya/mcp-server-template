#!/usr/bin/env python3
import os
import json
import uuid
from pathlib import Path
from fastmcp import FastMCP
from typing import List, Optional, Dict, Any, Union
import requests

try:
    from apify_client import ApifyClient
except Exception:  # library may not be installed yet
    ApifyClient = None  # type: ignore

try:
    import replicate
except Exception:  # library may not be installed yet
    replicate = None  # type: ignore

try:
    from PIL import Image
except Exception:  # library may not be installed yet
    Image = None  # type: ignore



# FastMCP server instance
mcp = FastMCP("Social Media Toolkit for Instagram & Tiktok")


# -------------------- Instagram / Apify helpers --------------------

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def notify_status(message: str) -> Dict[str, Any]:
    api_key = _env("POKE_API_KEY") or _env("NOTIFY_API_KEY")
    url = _env("NOTIFY_URL", "https://poke.com/api/v1/inbound-sms/webhook")
    if not api_key:
        return {"sent": False, "reason": "No API key configured", "message": message}
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"message": message},
            timeout=15,
        )
        return {"sent": resp.ok, "status_code": resp.status_code, "message": message}
    except Exception as e:
        return {"sent": False, "error": str(e), "message": message}


# -------------------- Image helpers --------------------

def _ensure_images_dir() -> Path:
    """Ensure images directory exists and return its path."""
    images_dir = Path("images")
    images_dir.mkdir(exist_ok=True)
    return images_dir


def _download_image(url: str, filename: str) -> Dict[str, Any]:
    """Download an image from URL to local file."""
    try:
        images_dir = _ensure_images_dir()
        file_path = images_dir / filename

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        with open(file_path, 'wb') as f:
            f.write(response.content)

        return {
            "success": True,
            "local_path": str(file_path),
            "size_bytes": len(response.content)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _check_existing_images() -> Dict[str, Any]:
    """Check for existing images from previous operations."""
    images_dir = Path("images")
    existing_images = []

    if images_dir.exists():
        for img_file in images_dir.glob("*"):
            if img_file.is_file() and img_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                existing_images.append({
                    "filename": img_file.name,
                    "path": str(img_file),
                    "size_bytes": img_file.stat().st_size
                })

    return {
        "count": len(existing_images),
        "images": existing_images
    }


@mcp.tool(
    description=(
        "Scrape Instagram via Apify instagram-scraper. "
        "Always asks to users which input to use, for example usernames or hastags or search and which proxy country to use."
        "Sends a completion notification after scraping."
        "Returns all scraped items in the response for further processing by other tools/agents."
    )
)
def instagram_scrape(
    usernames: Optional[List[str]] = None,
    hashtags: Optional[List[str]] = None,
    search: Optional[str] = None,
    results_limit: int = 50,
    proxy_country: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        if not any([usernames, hashtags, search]):
            raise ValueError("Provide at least one of usernames, hashtags, or search")
        token = _env("APIFY_TOKEN")
        if not token:
            raise RuntimeError("APIFY_TOKEN not configured")
        if ApifyClient is None:
            raise RuntimeError("apify-client is not installed")

        client = ApifyClient(token)
        run_input: Dict[str, Any] = {}
        if usernames:
            run_input["usernames"] = usernames
        if hashtags:
            run_input["hashtags"] = hashtags
        if search:
            run_input["search"] = search
        if results_limit:
            run_input["resultsLimit"] = int(results_limit)
        if proxy_country:
            run_input["proxy"] = {
                "useApifyProxy": True,
                "apifyProxyCountry": proxy_country,
            }

        run = client.actor("apify/instagram-scraper").call(run_input=run_input)
        dataset_id = run.get("defaultDatasetId")
        items: List[Dict[str, Any]] = []
        if dataset_id:
            for item in client.dataset(dataset_id).iterate_items():
                items.append(item)
        status = run.get("status", "UNKNOWN")

        notify = notify_status(f"Instagram scraping {status.lower()}: {len(items)} items")

        return {
            "status": status,
            "actor": "apify/instagram-scraper",
            "dataset_id": dataset_id,
            "items_count": len(items),
            "items": items,
            "notification": notify,
        }
    except Exception as e:
        notify_status(f"Instagram scraping failed: {e}")
        return {"error": str(e)}


@mcp.tool(
    description=(
        "Search and download free-to-use images from Unsplash. "
        "Provide search keywords, specify image count, orientation, and color filters. "
        "Downloads images locally and provides attribution information. "
        "Sends notification after completion."
    )
)
def image_fetch_unsplash(
    query: str,
    count: int = 5,
    orientation: Optional[str] = None,
    color: Optional[str] = None,
    download_images: bool = True,
) -> Dict[str, Any]:
    try:
        access_key = _env("UNSPLASH_ACCESS_KEY")
        if not access_key:
            raise RuntimeError("UNSPLASH_ACCESS_KEY not configured")

        # Check existing images first
        existing = _check_existing_images()

        # Build API request
        url = "https://api.unsplash.com/search/photos"
        params = {
            "query": query,
            "per_page": min(count, 30),  # Unsplash API limit
            "order_by": "relevant"
        }

        if orientation and orientation in ["landscape", "portrait", "squarish"]:
            params["orientation"] = orientation

        if color and color in ["black_and_white", "black", "white", "yellow", "orange", "red", "purple", "magenta", "green", "teal", "blue"]:
            params["color"] = color

        headers = {"Authorization": f"Client-ID {access_key}"}

        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        downloaded_images = []
        attribution_info = []

        for photo in results:
            photo_info = {
                "id": photo["id"],
                "description": photo.get("description") or photo.get("alt_description", ""),
                "photographer": photo["user"]["name"],
                "photographer_url": photo["user"]["links"]["html"],
                "unsplash_url": photo["links"]["html"],
                "download_url": photo["urls"]["regular"],
                "attribution": f"Photo by {photo['user']['name']} on Unsplash ({photo['links']['html']})"
            }
            attribution_info.append(photo_info)

            if download_images:
                # Generate unique filename
                filename = f"unsplash_{photo['id']}_{uuid.uuid4().hex[:8]}.jpg"
                download_result = _download_image(photo["urls"]["regular"], filename)

                if download_result["success"]:
                    downloaded_images.append({
                        **photo_info,
                        "local_path": download_result["local_path"],
                        "size_bytes": download_result["size_bytes"]
                    })

                    # Track download with Unsplash (required by API terms)
                    try:
                        track_url = photo["links"]["download_location"]
                        requests.get(track_url, headers=headers, timeout=10)
                    except Exception:
                        pass  # Don't fail if tracking fails

        notify_message = f"Unsplash search '{query}': {len(downloaded_images) if download_images else len(results)} images"
        if download_images:
            notify_message += f" downloaded"
        notify = notify_status(notify_message)

        return {
            "query": query,
            "total_found": data.get("total", 0),
            "returned_count": len(results),
            "downloaded_count": len(downloaded_images),
            "existing_images": existing,
            "images": downloaded_images if download_images else attribution_info,
            "attribution_required": True,
            "notification": notify
        }

    except Exception as e:
        notify_status(f"Unsplash image fetch failed: {e}")
        return {"error": str(e)}


@mcp.tool(
    description=(
        "Edit images using AI via Replicate's google/nano-banana model. "
        "Accepts image input (local file path or URL) and text prompts for modifications. "
        "Can process images from Instagram scrapes, Unsplash downloads, or local files. "
        "Returns edited image URL and saves locally. Sends notification after completion."
    )
)
def image_edit_replicate(
    image_input: str,
    prompt: str,
    additional_images: Optional[List[str]] = None,
    save_locally: bool = True,
) -> Dict[str, Any]:
    try:
        if not replicate:
            raise RuntimeError("replicate library is not installed")

        api_token = _env("REPLICATE_API_TOKEN")
        if not api_token:
            raise RuntimeError("REPLICATE_API_TOKEN not configured")

        # Check existing images first
        existing = _check_existing_images()

        # Prepare image input
        image_file = None
        if image_input.startswith(("http://", "https://")):
            # URL input
            image_file = image_input
        else:
            # Local file path
            image_path = Path(image_input)
            if not image_path.exists():
                # Try in images directory
                image_path = Path("images") / image_input
                if not image_path.exists():
                    raise FileNotFoundError(f"Image file not found: {image_input}")
            image_file = open(image_path, "rb")

        # Prepare model input
        model_input = {
            "image": image_file,
            "prompt": prompt
        }

        # Add additional images if provided
        if additional_images:
            processed_additional = []
            for img in additional_images:
                if img.startswith(("http://", "https://")):
                    processed_additional.append(img)
                else:
                    img_path = Path(img)
                    if not img_path.exists():
                        img_path = Path("images") / img
                    if img_path.exists():
                        processed_additional.append(open(img_path, "rb"))

            if processed_additional:
                model_input["additional_images"] = processed_additional

        # Run the model
        output = replicate.run(
            "google/nano-banana",
            input=model_input
        )

        # Close file handles if opened
        if hasattr(image_file, 'close'):
            image_file.close()

        # Process output
        result_info = {
            "model": "google/nano-banana",
            "prompt": prompt,
            "input_image": image_input,
            "existing_images": existing
        }

        if output:
            if hasattr(output, 'read'):
                # FileOutput object
                if save_locally:
                    images_dir = _ensure_images_dir()
                    filename = f"edited_{uuid.uuid4().hex[:8]}.png"
                    local_path = images_dir / filename

                    with open(local_path, 'wb') as f:
                        f.write(output.read())

                    result_info.update({
                        "success": True,
                        "local_path": str(local_path),
                        "size_bytes": local_path.stat().st_size,
                        "output_url": None
                    })
                else:
                    result_info.update({
                        "success": True,
                        "output_data": output.read(),
                        "local_path": None
                    })
            elif isinstance(output, str) and output.startswith("http"):
                # URL output
                result_info.update({
                    "success": True,
                    "output_url": output,
                    "local_path": None
                })

                if save_locally:
                    filename = f"edited_{uuid.uuid4().hex[:8]}.png"
                    download_result = _download_image(output, filename)
                    if download_result["success"]:
                        result_info.update({
                            "local_path": download_result["local_path"],
                            "size_bytes": download_result["size_bytes"]
                        })
            else:
                result_info.update({
                    "success": True,
                    "output": str(output),
                    "local_path": None
                })
        else:
            result_info.update({
                "success": False,
                "error": "No output received from model"
            })

        notify_message = f"Image editing {'completed' if result_info.get('success') else 'failed'}: {prompt[:50]}..."
        notify = notify_status(notify_message)
        result_info["notification"] = notify

        return result_info

    except Exception as e:
        notify_status(f"Image editing failed: {e}")
        return {"error": str(e)}


@mcp.tool(description=(
    "Social Media Toolkit for Instagram & Tiktok, it scrapes Instagram profiles, hashtags, and search terms."
    "It also do creative writing for social media posts."
    "Generate Instagram posts from a given prompt using Gemini Nano Banana"
))
def get_server_info() -> dict:
    return {
        "server_name": "Social Media Toolkit for Instagram & Tiktok",
        "version": "0.0.1",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": os.sys.version.split()[0]
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    print(f"Starting FastMCP server on {host}:{port}")

    mcp.run(
        transport="http",
        host=host,
        port=port
    )
