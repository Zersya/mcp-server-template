# Instagram Scraping Timeout Fix - Async Implementation

## Problem
The Instagram scraping functionality was experiencing MCP timeout errors (-32001) due to synchronous, blocking operations that could take several minutes to complete. This was causing the MCP server to timeout while waiting for the scraping operations.

## Solution
Converted the Instagram scraping functionality from synchronous to asynchronous operations to prevent blocking the event loop and allow for proper timeout handling.

## Changes Made

### 1. Dependencies
- Added `aiohttp>=3.9.0` to `requirements.txt` for async HTTP requests
- Added `asyncio` import for async/await patterns

### 2. New Async Functions

#### `_late_api_request_async()`
- Async version of `_late_api_request()` using `aiohttp.ClientSession`
- Configurable timeouts via environment variables:
  - `MCP_HTTP_TOTAL_TIMEOUT` (default: 600s)
  - `MCP_HTTP_CONNECT_TIMEOUT` (default: 30s) 
  - `MCP_HTTP_READ_TIMEOUT` (default: 120s)
- Enhanced error handling for timeout scenarios
- Proper retry logic with exponential backoff

#### `notify_status_async()`
- Async version of `notify_status()` using `aiohttp`
- Falls back to sync version if aiohttp is unavailable
- Non-blocking notification sending

### 3. Converted Functions to Async

#### `instagram_scrape()`
- Main scraping function converted to async
- Apify client operations wrapped in `asyncio.to_thread()` to avoid blocking
- Knowledge base operations wrapped in `asyncio.to_thread()`
- Uses async notification function

#### `instagram_get_accounts()`
- Converted to async
- Uses `_late_api_request_async()` for API calls

#### `instagram_post_schedule()`
- Converted to async  
- Uses `_late_api_request_async()` for API calls
- Uses async notification function

### 4. Timeout Configuration
Added environment variables for timeout configuration:
- `MCP_HTTP_TOTAL_TIMEOUT`: Total request timeout (default: 600s for scraping)
- `MCP_HTTP_CONNECT_TIMEOUT`: Connection timeout (default: 30s)
- `MCP_HTTP_READ_TIMEOUT`: Socket read timeout (default: 120s)

### 5. Error Handling Improvements
- Specific error messages for different timeout scenarios
- Better distinction between connection, read, and total timeouts
- Helpful suggestions for resolving timeout issues

## Benefits

1. **No More MCP Timeouts**: Long-running scraping operations no longer block the MCP server
2. **Better Performance**: Async operations allow other requests to be processed concurrently
3. **Configurable Timeouts**: Users can adjust timeout values based on their needs
4. **Better Error Messages**: Clear feedback when timeouts occur with suggestions for resolution
5. **Backward Compatibility**: All existing functionality preserved

## Usage

The functions work exactly the same as before from the user perspective, but now handle long-running operations asynchronously:

```python
# These functions are now async but the MCP interface handles this automatically
await instagram_scrape(direct_urls=["instagram.com/username"])
await instagram_get_accounts()
await instagram_post_schedule(content="Hello", instagram_account_id="123", image_source="image.jpg")
```

## Environment Variables

Set these environment variables to customize timeout behavior:

```bash
# For very slow networks or large scraping operations
export MCP_HTTP_TOTAL_TIMEOUT=900  # 15 minutes

# For faster connection requirements
export MCP_HTTP_CONNECT_TIMEOUT=10  # 10 seconds

# For faster read requirements  
export MCP_HTTP_READ_TIMEOUT=60     # 1 minute
```

## Testing

Run the test script to verify the async implementation:

```bash
python test_async.py
```

This will test:
- Async HTTP request functionality
- Timeout handling
- Environment variable configuration
- Notification system

## Commands to Run

After making these changes, install the new dependency:

```bash
pip install aiohttp>=3.9.0
```

Then restart your MCP server:

```bash
python src/server.py
```

The Instagram scraping timeout issue should now be resolved!
