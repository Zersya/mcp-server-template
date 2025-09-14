#!/usr/bin/env python3
import os
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
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

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except Exception:  # library may not be installed yet
    boto3 = None  # type: ignore
    ClientError = Exception  # type: ignore
    NoCredentialsError = Exception  # type: ignore



# FastMCP server instance
mcp = FastMCP("Social Media Toolkit for Instagram & Tiktok")


# -------------------- Instagram / Apify helpers --------------------

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def notify_status(message: str, image_urls: Optional[List[str]] = None, expires_hours: Optional[int] = None) -> Dict[str, Any]:
    api_key = _env("POKE_API_KEY") or _env("NOTIFY_API_KEY")
    url = _env("NOTIFY_URL", "https://poke.com/api/v1/inbound-sms/webhook")
    if not api_key:
        return {"sent": False, "reason": "No API key configured", "message": message}

    # Enhance message with image URLs if provided
    enhanced_message = message
    if image_urls:
        url_text = ", ".join(image_urls[:3])  # Limit to 3 URLs for SMS length
        if len(image_urls) > 3:
            url_text += f" (+{len(image_urls) - 3} more)"

        expiry_text = ""
        if expires_hours:
            expiry_text = f" - expires in {expires_hours}h"

        enhanced_message = f"{message}\nImages: {url_text}{expiry_text}"

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"message": enhanced_message},
            timeout=15,
        )
        return {
            "sent": resp.ok,
            "status_code": resp.status_code,
            "message": enhanced_message,
            "image_urls_included": len(image_urls) if image_urls else 0
        }
    except Exception as e:
        return {"sent": False, "error": str(e), "message": enhanced_message}


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


# -------------------- Cloudflare R2 helpers --------------------

def _get_r2_client():
    """Get configured R2 client or None if not available."""
    if not boto3:
        return None

    account_id = _env("CLOUDFLARE_R2_ACCOUNT_ID")
    access_key = _env("CLOUDFLARE_R2_ACCESS_KEY_ID")
    secret_key = _env("CLOUDFLARE_R2_SECRET_ACCESS_KEY")

    if not all([account_id, access_key, secret_key]):
        return None

    try:
        return boto3.client(
            's3',
            endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='auto'
        )
    except Exception:
        return None


def _upload_to_r2(local_path: str, folder: str, filename: str) -> Dict[str, Any]:
    """Upload file to Cloudflare R2 storage."""
    try:
        client = _get_r2_client()
        if not client:
            return {"success": False, "error": "R2 client not configured"}

        bucket_name = _env("CLOUDFLARE_R2_BUCKET_NAME")
        if not bucket_name:
            return {"success": False, "error": "R2 bucket name not configured"}

        # Construct R2 key with folder structure
        r2_key = f"{folder.strip('/')}/{filename}"

        # Upload file
        with open(local_path, 'rb') as f:
            client.upload_fileobj(f, bucket_name, r2_key)

        # Generate presigned URL (24 hours expiration)
        expires_in = 24 * 60 * 60  # 24 hours in seconds
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        try:
            public_url = client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': r2_key},
                ExpiresIn=expires_in
            )
        except Exception:
            # Fallback to custom domain if available
            custom_domain = _env("CLOUDFLARE_R2_PUBLIC_DOMAIN")
            if custom_domain:
                public_url = f"https://{custom_domain}/{r2_key}"
            else:
                public_url = f"https://{bucket_name}.r2.dev/{r2_key}"

        return {
            "success": True,
            "r2_key": r2_key,
            "r2_url": f"s3://{bucket_name}/{r2_key}",
            "public_url": public_url,
            "expires_at": expires_at.isoformat() + "Z",
            "expires_in_hours": 24
        }

    except ClientError as e:
        return {"success": False, "error": f"R2 upload failed: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Upload error: {e}"}


@mcp.tool(
    description=(
        "Scrape Instagram via Apify instagram-scraper. "
        "Accepts usernames (automatically converted to URLs), profile URLs, or post URLs. "
        "Plain usernames like 'kugie.app' are automatically converted to 'https://www.instagram.com/kugie.app/'. "
        "Can scrape profiles, posts, or specific content based on the URLs provided. "
        "Sends a completion notification after scraping."
        "Returns all scraped items in the response for further processing by other tools/agents."
    )
)
def instagram_scrape(
    direct_urls: Optional[List[str]] = None,
    results_limit: int = 200,
    results_type: str = "posts",
    add_parent_data: bool = False,
    enhance_user_search_with_facebook_page: bool = False,
    is_user_reel_feed_url: bool = False,
    is_user_tagged_feed_url: bool = False,
    search_type: Optional[str] = None,
    search_query: Optional[str] = None,
    search_limit: int = 1,
    proxy_country: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        # Validate input: either direct URLs (or usernames to convert), or search parameters
        has_direct = bool(direct_urls and len(direct_urls) > 0)
        has_search = bool(search_type and search_query)
        if not (has_direct or has_search):
            raise ValueError("Provide either direct_urls (usernames or URLs) or both search_type and search_query")

        token = _env("APIFY_TOKEN")
        if not token:
            raise RuntimeError("APIFY_TOKEN not configured")
        if ApifyClient is None:
            raise RuntimeError("apify-client is not installed")

        # Convert plain usernames in direct_urls to Instagram URLs
        processed_direct_urls: List[str] = []
        conversions: List[str] = []
        if has_direct:
            for u in direct_urls or []:
                if isinstance(u, str) and u.startswith(("http://", "https://")):
                    processed_direct_urls.append(u)
                else:
                    clean = (u or "").lstrip('@').strip()
                    if not clean:
                        continue
                    url = f"https://www.instagram.com/{clean}/"
                    processed_direct_urls.append(url)
                    conversions.append(f"{u} -> {url}")
            if conversions:
                print(f"Direct URL conversions: {conversions}")

        client = ApifyClient(token)
        run_input: Dict[str, Any] = {
            "resultsLimit": int(results_limit),
            "resultsType": results_type,
            "addParentData": bool(add_parent_data),
            "enhanceUserSearchWithFacebookPage": bool(enhance_user_search_with_facebook_page),
            "isUserReelFeedURL": bool(is_user_reel_feed_url),
            "isUserTaggedFeedURL": bool(is_user_tagged_feed_url),
        }

        if processed_direct_urls:
            run_input["directUrls"] = processed_direct_urls

        if has_search:
            run_input["searchType"] = search_type
            run_input["search"] = search_query
            run_input["searchLimit"] = int(search_limit)

        # Add proxy configuration if specified
        if proxy_country:
            run_input["proxy"] = {
                "useApifyProxy": True,
                "apifyProxyCountry": proxy_country,
            }

        run = client.actor("apify/instagram-scraper").call(run_input=run_input)

        # Check if run was successful
        if not run:
            raise RuntimeError("Apify actor run failed - no response received")

        # Debug: log the run response structure
        print(f"Apify run response: {run}")

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            # Try alternative key names
            dataset_id = run.get("datasetId") or run.get("dataset_id")
            if not dataset_id:
                raise RuntimeError(f"Apify actor run failed - no dataset ID returned. Run response: {run}")

        # Retrieve only a sample of items in the initial response to keep payloads small
        items: List[Dict[str, Any]] = []
        truncated = False
        max_items = int((_env("MCP_SCRAPE_ITEMS_MAX", "50") or "50"))
        try:
            for item in client.dataset(dataset_id).iterate_items():
                items.append(item)
                if len(items) >= max_items:
                    truncated = True
                    break
        except Exception as dataset_error:
            raise RuntimeError(f"Failed to retrieve dataset items: {dataset_error}")

        status = run.get("status", "UNKNOWN")

        # Check if the run failed
        if status in ["FAILED", "ABORTED", "TIMED-OUT"]:
            error_message = run.get("statusMessage", "Unknown error")
            raise RuntimeError(f"Apify actor run {status}: {error_message}")

        notify = notify_status(f"Instagram scraping {status.lower()}: {len(items)} items")

        return {
            "status": status,
            "actor": "apify/instagram-scraper",
            "dataset_id": dataset_id,
            "items_returned": len(items),
            "items_truncated": truncated,
            "items_max_in_response": max_items,
            "items": items,
            "notification": notify,
            "input_processing": {
                "original_direct_urls": direct_urls or [],
                "processed_direct_urls": processed_direct_urls,
                "conversions": conversions if conversions else "No conversions needed",
                "search": {
                    "search_type": search_type,
                    "search_query": search_query,
                    "search_limit": search_limit
                } if has_search else None
            },
            "paging": {
                "hint": "Use instagram_dataset_fetch(dataset_id, offset, limit) to page through all items",
                "next_offset": len(items) if truncated else None,
                "default_limit": 100
            },
            "run_info": {
                "id": run.get("id"),
                "status": status,
                "started_at": run.get("startedAt"),
                "finished_at": run.get("FinishedAt") or run.get("finishedAt"),
                "usage": run.get("usage", {})
            }
        }
    except Exception as e:
        notify_status(f"Instagram scraping failed: {e}")
        return {"error": str(e)}


@mcp.tool(
    description=(
        "Fetch items from an Apify dataset produced by instagram_scrape with pagination. "
        "Use this to page through all results without large payloads."
    )
)
def instagram_dataset_fetch(
    dataset_id: str,
    offset: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    try:
        token = _env("APIFY_TOKEN")
        if not token:
            raise RuntimeError("APIFY_TOKEN not configured")
        if ApifyClient is None:
            raise RuntimeError("apify-client is not installed")

        client = ApifyClient(token)
        ds = client.dataset(dataset_id)

        items: List[Dict[str, Any]] = []
        used_list_api = False
        try:
            # Prefer list_items if available for efficient paging
            if hasattr(ds, "list_items"):
                used_list_api = True
                resp = ds.list_items(limit=int(limit), offset=int(offset))
                items = resp.get("items", []) if isinstance(resp, dict) else resp or []
            else:
                # Fallback: iterate and slice
                idx = 0
                for itm in ds.iterate_items():
                    if idx >= offset and len(items) < limit:
                        items.append(itm)
                    idx += 1
                    if len(items) >= limit:
                        break
        except Exception as e:
            raise RuntimeError(f"Failed to fetch dataset items: {e}")

        next_offset = offset + len(items)
        more_available = len(items) == limit

        return {
            "dataset_id": dataset_id,
            "items_count": len(items),
            "items": items,
            "offset": offset,
            "limit": limit,
            "next_offset": next_offset if more_available else None,
            "paging_method": "list_items" if used_list_api else "iterate_items",
        }
    except Exception as e:
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
                    image_data = {
                        **photo_info,
                        "local_path": download_result["local_path"],
                        "size_bytes": download_result["size_bytes"]
                    }

                    # Upload to R2 storage
                    r2_result = _upload_to_r2(
                        download_result["local_path"],
                        "fetched",
                        filename
                    )

                    if r2_result["success"]:
                        image_data.update({
                            "r2_url": r2_result["r2_url"],
                            "public_url": r2_result["public_url"],
                            "expires_at": r2_result["expires_at"],
                            "expires_in_hours": r2_result["expires_in_hours"]
                        })
                    else:
                        image_data["r2_error"] = r2_result["error"]

                    downloaded_images.append(image_data)

                    # Track download with Unsplash (required by API terms)
                    try:
                        track_url = photo["links"]["download_location"]
                        requests.get(track_url, headers=headers, timeout=10)
                    except Exception:
                        pass  # Don't fail if tracking fails

        notify_message = f"Unsplash search '{query}': {len(downloaded_images) if download_images else len(results)} images"
        if download_images:
            notify_message += f" downloaded"

        # Collect public URLs for SMS notification
        public_urls = []
        expires_hours = None
        if download_images:
            for img in downloaded_images:
                if img.get("public_url"):
                    public_urls.append(img["public_url"])
                    if not expires_hours and img.get("expires_in_hours"):
                        expires_hours = img["expires_in_hours"]

        notify = notify_status(notify_message, public_urls, expires_hours)

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

                    # Upload to R2 storage
                    r2_result = _upload_to_r2(str(local_path), "edited", filename)
                    if r2_result["success"]:
                        result_info.update({
                            "r2_url": r2_result["r2_url"],
                            "public_url": r2_result["public_url"],
                            "expires_at": r2_result["expires_at"],
                            "expires_in_hours": r2_result["expires_in_hours"]
                        })
                    else:
                        result_info["r2_error"] = r2_result["error"]
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

                        # Upload to R2 storage
                        r2_result = _upload_to_r2(download_result["local_path"], "edited", filename)
                        if r2_result["success"]:
                            result_info.update({
                                "r2_url": r2_result["r2_url"],
                                "public_url": r2_result["public_url"],
                                "expires_at": r2_result["expires_at"],
                                "expires_in_hours": r2_result["expires_in_hours"]
                            })
                        else:
                            result_info["r2_error"] = r2_result["error"]
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

        # Include public URL in SMS notification if available
        public_urls = []
        expires_hours = None
        if result_info.get("success") and result_info.get("public_url"):
            public_urls.append(result_info["public_url"])
            expires_hours = result_info.get("expires_in_hours")

        notify = notify_status(notify_message, public_urls, expires_hours)
        result_info["notification"] = notify

        return result_info

    except Exception as e:
        notify_status(f"Image editing failed: {e}")
        return {"error": str(e)}


def _extract_image_url_from_tool_response(tool_response: Dict[str, Any]) -> Optional[str]:
    """Extract the best image URL from responses from image_fetch_unsplash or image_edit_replicate."""
    if not isinstance(tool_response, dict):
        return None

    # For image_edit_replicate responses
    if "public_url" in tool_response:
        return tool_response["public_url"]

    # For image_fetch_unsplash responses
    if "images" in tool_response and isinstance(tool_response["images"], list):
        for image in tool_response["images"]:
            if isinstance(image, dict) and "public_url" in image:
                return image["public_url"]

    return None


@mcp.tool(
    description=(
        "Schedule Instagram posts using Late.dev API. "
        "Supports posting images from local files, R2 storage URLs, or external URLs. "
        "Can schedule posts for later or publish immediately. "
        "Requires Instagram Business account and Late.dev API key. "
        "Sends notification with post URL after successful scheduling. "
        "For best results, use R2 URLs from image_fetch_unsplash or image_edit_replicate tools."
    )
)
def instagram_post_schedule(
    content: str,
    image_source: str,
    instagram_account_id: str,
    schedule_time: Optional[str] = None,
    timezone: str = "UTC",
    publish_now: bool = False,
    content_type: str = "post",
    collaborators: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Schedule Instagram posts via Late.dev API with image support."""
    try:
        # Validate API key
        api_key = _env("LATE_DEV_API_KEY")
        if not api_key:
            raise RuntimeError("LATE_DEV_API_KEY not configured")

        # Validate required parameters
        if not content.strip():
            raise ValueError("Content cannot be empty")

        if not instagram_account_id.strip():
            raise ValueError("Instagram account ID is required")

        # Process image source
        image_url = None
        local_file_info = None

        if image_source:
            if image_source.startswith(("http://", "https://")):
                # External URL (including R2 URLs)
                image_url = image_source
            else:
                # Local file path - try to upload to R2 first
                image_path = Path(image_source)
                if not image_path.exists():
                    # Try images directory
                    image_path = Path("images") / image_source

                if not image_path.exists():
                    raise FileNotFoundError(f"Image file not found: {image_source}")

                # Upload to R2 for better reliability
                filename = image_path.name
                r2_result = _upload_to_r2(str(image_path), "instagram", filename)

                if r2_result["success"]:
                    image_url = r2_result["public_url"]
                    local_file_info = {
                        "local_path": str(image_path),
                        "r2_key": r2_result["r2_key"],
                        "r2_url": r2_result["r2_url"],
                        "expires_at": r2_result["expires_at"]
                    }
                else:
                    # Fallback: provide guidance for manual URL usage
                    raise ValueError(
                        f"Failed to upload image to R2: {r2_result['error']}. "
                        "Please use image_fetch_unsplash or image_edit_replicate tools "
                        "which automatically provide R2 URLs, or provide a direct image URL."
                    )

        # Build Late.dev API request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Build platform-specific data
        platform_data = {
            "platform": "instagram",
            "accountId": instagram_account_id
        }

        # Add platform-specific options
        if content_type == "story":
            platform_data["platformSpecificData"] = {"contentType": "story"}
        elif collaborators:
            platform_data["platformSpecificData"] = {"collaborators": collaborators}

        # Build request payload
        payload = {
            "content": content,
            "platforms": [platform_data]
        }

        # Add media if image provided
        if image_url:
            payload["mediaItems"] = [
                {
                    "type": "image",
                    "url": image_url
                }
            ]

        # Handle scheduling
        if not publish_now and schedule_time:
            payload["scheduledFor"] = schedule_time
            payload["timezone"] = timezone
        elif publish_now:
            # For immediate posting, don't include scheduledFor
            pass

        # Make API request to Late.dev
        response = requests.post(
            "https://getlate.dev/api/v1/posts",
            headers=headers,
            json=payload,
            timeout=30
        )

        if not response.ok:
            error_msg = f"Late.dev API error: HTTP {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg += f" - {error_data['error']}"
            except:
                error_msg += f" - {response.text}"

            # Handle specific Instagram errors
            if response.status_code == 403:
                error_msg += " (Check if Instagram account is Business type and properly connected)"
            elif response.status_code == 401:
                error_msg += " (Invalid Late.dev API key)"

            raise RuntimeError(error_msg)

        result_data = response.json()

        # Extract post information
        post_info = {
            "success": True,
            "content": content,
            "image_url": image_url,
            "instagram_account_id": instagram_account_id,
            "content_type": content_type,
            "scheduled": not publish_now,
            "schedule_time": schedule_time if not publish_now else None,
            "timezone": timezone,
            "late_dev_response": result_data
        }

        # Add local file info if available
        if local_file_info:
            post_info["local_file_info"] = local_file_info

        # Extract post URL if available
        post_url = None
        if "post" in result_data and "url" in result_data["post"]:
            post_url = result_data["post"]["url"]
            post_info["post_url"] = post_url

        # Send notification
        notify_message = f"Instagram post {'scheduled' if not publish_now else 'published'}: {content[:50]}..."
        if post_url:
            notify_message += f"\nPost: {post_url}"

        notify_urls = [post_url] if post_url else []
        notify = notify_status(notify_message, notify_urls)
        post_info["notification"] = notify

        return post_info

    except Exception as e:
        notify_status(f"Instagram post scheduling failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    print(f"Starting FastMCP server on {host}:{port}")

    mcp.run(
        transport="http",
        host=host,
        port=port
    )
