# Image Search Tool

This tool uses Google Custom Search API to search for images based on keywords, and optionally uses Google Gemini AI to evaluate and select the best images.

## Features

- Load keyword lists from JSON files
- Search for images using Google Custom Search API
- Optional: Evaluate and select best images using Gemini 2.5 Flash model
- Automatically download images and name them by ID and keyword
- Automatic image validation and format conversion (PNG/WebP → JPEG)
- Skip already downloaded images to save API quota
- Retry logic with exponential backoff for API failures
- Rate limiting and cooldown periods to prevent API errors

## Installation

1. Create a virtual environment (if you haven't already):
```bash
python3 -m venv .venv
```

2. Activate the virtual environment and install dependencies:
```bash
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

## Configuration

Set the following configurations in the `.env` file:

```bash
# API Keys
GOOGLE_AI_API_KEY=your_gemini_api_key_here
GOOGLE_CUSTOM_API_KEY=your_custom_search_api_key_here
GOOGLE_CX=your_search_engine_id_here

# Gemini Evaluation (default: false)
USE_GEMINI_EVAL=true

# Image Search Configuration
IMG_SIZE=xxlarge          # huge, icon, large, medium, small, xlarge, xxlarge
IMG_TYPE=photo            # clipart, face, lineart, photo, animated
NUM_RESULTS=5             # Number of search results (max 10)

# Keyword Processing Range
START_INDEX=0             # Starting keyword index
END_INDEX=61              # Ending keyword index (exclusive)

# Optional Configuration
# IMG_COLOR_TYPE=color    # color, gray, mono, trans
# IMG_DOMINANT_COLOR=blue # black, blue, brown, gray, green, orange, pink, purple, red, teal, white, yellow
# FILE_TYPE=jpg           # jpg, gif, png, bmp, svg, webp, ico
```

### Getting API Keys

1. **Google AI (Gemini) API Key**:
   - Visit https://makersuite.google.com/app/apikey
   - Create a new API key

2. **Google Custom Search API Key**:
   - Visit https://console.cloud.google.com/apis/credentials
   - Create an API key and enable "Custom Search API"

3. **Google Search Engine ID (CX)**:
   - Visit https://programmablesearchengine.google.com/
   - Create a new search engine
   - In "Sites to search", enter `*` and check "Search the entire web"
   - Copy the "Search engine ID"

## Usage

### Basic Usage (without Gemini Evaluation)

```bash
.venv/bin/python image_tool.py
```

This will:
- Read keywords from `keywords.json` based on START_INDEX and END_INDEX
- Search for images for each keyword
- Download the first image to the `output/` directory

### Using Gemini to Evaluate Best Images

Set in `.env`:
```bash
USE_GEMINI_EVAL=true
```

Then run:
```bash
.venv/bin/python image_tool.py
```

This will use Gemini AI to analyze each search result and select the best image.

### Custom Image Search Parameters

You can adjust the following parameters in the `.env` file:

#### IMG_SIZE - Image Size
- `icon` - Icon-sized images
- `small` - Small images
- `medium` - Medium images
- `large` - Large images
- `xlarge` - Extra large images
- `xxlarge` - Extremely large images (recommended for highest quality)
- `huge` - Huge images

#### IMG_TYPE - Image Type
- `photo` - Photographic images (default, recommended for realistic scenes)
- `face` - Face photos
- `clipart` - Clipart images
- `lineart` - Line art images
- `animated` - Animated images

#### IMG_COLOR_TYPE - Color Type (optional)
- `color` - Color images
- `gray` - Grayscale images
- `mono` - Monochrome images
- `trans` - Transparent background images

#### IMG_DOMINANT_COLOR - Dominant Color (optional)
Available colors: `black`, `blue`, `brown`, `gray`, `green`, `orange`, `pink`, `purple`, `red`, `teal`, `white`, `yellow`

For example, to search for images with blue as the dominant color:
```bash
IMG_DOMINANT_COLOR=blue
```

#### FILE_TYPE - File Format (optional)
Available formats: `jpg`, `png`, `gif`, `bmp`, `svg`, `webp`, `ico`

For example, to search only for PNG format images:
```bash
FILE_TYPE=png
```

#### NUM_RESULTS - Number of Search Results
Set the number of images returned for each keyword search (max 10):
```bash
NUM_RESULTS=10
```

#### START_INDEX and END_INDEX - Keyword Range
Process keywords from START_INDEX to END_INDEX (exclusive):
```bash
START_INDEX=0     # First keyword index
END_INDEX=30      # Process keywords 0-29
```

Examples:
- `0 to 30` = First 30 keywords (1-1 to 1-30)
- `30 to 60` = Keywords 31-60 (including header + 2-1 to 2-29)
- `0 to 61` = All keywords

### Example Configurations

**Search for high-quality photos (default):**
```bash
IMG_SIZE=xxlarge
IMG_TYPE=photo
NUM_RESULTS=5
```

**Search for clipart with transparent backgrounds:**
```bash
IMG_SIZE=large
IMG_TYPE=clipart
IMG_COLOR_TYPE=trans
FILE_TYPE=png
```

**Search for face photos with blue tones:**
```bash
IMG_SIZE=xlarge
IMG_TYPE=face
IMG_DOMINANT_COLOR=blue
```

## Keywords File Format

`keywords.json` is a JSON array containing the following fields:

```json
[
  {
    "id": "1-1",
    "keyword": "person sitting on bench outdoors",
    "keyword_formatted": "person sitting on bench outdoors",
    "prompt_cn": "Chinese prompt",
    "prompt_en": "English prompt"
  }
]
```

## Output

Images are saved in the `output/` directory with the naming format:
```
{id}_{keyword_formatted}.jpg
```

For example: `1-1_person_sitting_on_bench_outdoors.jpg`

All downloaded images are automatically converted to JPEG format with high quality (95%), regardless of the original format (PNG, WebP, etc.). Transparent images are converted with a white background.

## Limitations

- Google Custom Search API has daily quota limits (Free tier: 100 queries/day)
- Maximum 10 images per search request
- Gemini API has rate limits (15 requests per minute)
- The tool includes automatic cooldown periods every 10 keywords to prevent rate limiting

## Utilities

### Fix Corrupted Images

Run the `fix_corrupted_images.py` script to detect and remove corrupted images:

```bash
.venv/bin/python fix_corrupted_images.py
```

This will:
- Check all downloaded images for validity
- Detect HTML error pages, invalid formats, and files that are too small
- Optionally delete corrupted files so they can be re-downloaded

## Troubleshooting

### API Key Errors
Make sure all API keys are correctly set in the `.env` file.

### Gemini Evaluation Failures
If Gemini evaluation encounters issues, set `USE_GEMINI_EVAL=false` to disable it.

### Search Quota Exhausted
Google Custom Search API has daily limits. Consider upgrading to a paid plan or wait for the quota to reset.

### 500 Internal Server Errors from Gemini
The tool includes built-in retry logic and rate limiting to minimize these errors. If they persist:
- Reduce `NUM_RESULTS` from 5 to 3
- Increase cooldown periods in the code
- Disable Gemini evaluation temporarily with `USE_GEMINI_EVAL=false`

### Corrupted or Invalid Images
The tool now includes automatic validation and format conversion:
- Files smaller than 1KB are rejected
- Invalid image formats trigger automatic retry with alternative images
- PNG/WebP formats are automatically converted to JPEG
- Run `fix_corrupted_images.py` to clean up any corrupted files from previous runs
