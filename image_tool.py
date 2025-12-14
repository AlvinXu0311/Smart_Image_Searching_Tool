import json
import os
import requests
import time
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

# Load environment variables from .env file
load_dotenv()

# Set up API keys
GOOGLE_CUSTOM_API_KEY = os.environ.get('GOOGLE_CUSTOM_API_KEY')  # For Google Custom Search
GOOGLE_CX = os.environ.get('GOOGLE_CX')  # Custom Search Engine ID
GOOGLE_AI_API_KEY = os.environ.get('GOOGLE_AI_API_KEY')  # For Gemini

if not all([GOOGLE_CUSTOM_API_KEY, GOOGLE_CX, GOOGLE_AI_API_KEY]):
    raise ValueError("Please set GOOGLE_CUSTOM_API_KEY, GOOGLE_CX, and GOOGLE_AI_API_KEY in the .env file")

# Configure Gemini
genai.configure(api_key=GOOGLE_AI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')  # Use latest vision model

def search_images(keyword, num=5, img_size='huge', img_type='photo',
                  img_color_type=None, img_dominant_color=None, file_type=None, exclude_watermark=True):
    """
    Search for images using Google Custom Search API

    Args:
        keyword: Search query
        num: Number of results (max 10 per request)
        img_size: Image size
            - 'huge': Very large images
            - 'icon': Icon-sized images
            - 'large': Large images (default)
            - 'medium': Medium images
            - 'small': Small images
            - 'xlarge': Extra large images
            - 'xxlarge': Extremely large images
        img_type: Image type
            - 'clipart': Clipart images
            - 'face': Face images
            - 'lineart': Line art images
            - 'photo': Photographic images (default)
            - 'animated': Animated images
        img_color_type: Image color type
            - 'color': Color images
            - 'gray': Grayscale images
            - 'mono': Monochrome images
            - 'trans': Transparent images
        img_dominant_color: Dominant color
            - 'black', 'blue', 'brown', 'gray', 'green', 'orange',
              'pink', 'purple', 'red', 'teal', 'white', 'yellow'
        file_type: File format
            - 'jpg', 'gif', 'png', 'bmp', 'svg', 'webp', 'ico'
        exclude_watermark: Exclude images with watermarks (default: True)
    """
    url = "https://www.googleapis.com/customsearch/v1"

    # Add exclusion terms for watermarked images
    search_query = keyword
    if exclude_watermark:
        search_query = f'{keyword} -watermark -"stock photo" -shutterstock -getty -istockphoto -alamy'

    params = {
        "key": GOOGLE_CUSTOM_API_KEY,
        "cx": GOOGLE_CX,
        "q": search_query,
        "searchType": "image",
        "num": min(num, 10),  # Max 10 results per request
        "imgSize": img_size,
        "imgType": img_type,
        "safe": "off"  # No SafeSearch filtering
    }

    # Add optional parameters
    if img_color_type:
        params["imgColorType"] = img_color_type
    if img_dominant_color:
        params["imgDominantColor"] = img_dominant_color
    if file_type:
        params["fileType"] = file_type

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()

        # Format results to match expected structure
        images = []
        for item in results.get('items', []):
            images.append({
                'original': item.get('link'),
                'link': item.get('link'),
                'thumbnail': item.get('image', {}).get('thumbnailLink'),
                'title': item.get('title'),
                'source': item.get('displayLink')
            })
        return images
    except requests.exceptions.RequestException as e:
        print(f"Error searching for images: {e}")
        return []

def download_image(url, filename, max_retries=3):
    """Download image with retry logic, validation, and format conversion"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                content = response.content

                # Validate image content size
                if len(content) < 1024:  # Less than 1KB is suspicious
                    if attempt < max_retries - 1:
                        print(f"  Downloaded file too small ({len(content)} bytes), retrying...")
                        time.sleep(1)
                        continue
                    else:
                        print(f"  Downloaded file too small ({len(content)} bytes)")
                        return False

                # Try to open image with Pillow to validate and convert if needed
                try:
                    img = Image.open(BytesIO(content))

                    # Convert to RGB if necessary (handles PNG, WebP, etc.)
                    if img.mode in ('RGBA', 'LA', 'P'):
                        # Create white background for transparent images
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Save as JPEG
                    img.save(filename, 'JPEG', quality=95)
                    return True

                except Exception as img_error:
                    if attempt < max_retries - 1:
                        print(f"  Invalid image format, retrying...")
                        time.sleep(1)
                        continue
                    else:
                        print(f"  Cannot process image: {img_error}")
                        return False

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Download attempt {attempt + 1} failed, retrying...")
                time.sleep(1)
            else:
                print(f"  Download failed after {max_retries} attempts: {e}")
    return False

def evaluate_best_image(images, keyword, max_retries=3):
    """Evaluate images using Gemini with retry logic and rate limiting"""
    # Download images temporarily
    temp_files = []
    for i, img in enumerate(images):
        url = img.get('original', img.get('link', ''))
        temp_file = f'temp_{i}.jpg'
        if download_image(url, temp_file, max_retries=2):
            temp_files.append(temp_file)
        else:
            temp_files.append(None)

    # Prepare prompt
    prompt = f"Here are {len(images)} images searched for the keyword '{keyword}'. Which one is the best match? Choose the index (0 to {len(images)-1}) of the best image and explain why briefly."

    # Upload images to Gemini
    uploaded_files = []
    for temp_file in temp_files:
        if temp_file:
            uploaded_files.append(genai.upload_file(temp_file))
            time.sleep(0.5)  # Increased delay to respect rate limits
        else:
            uploaded_files.append(None)

    # Add delay before generation to space out API calls
    time.sleep(2)

    # Generate content with retry logic
    best_index = 0
    for attempt in range(max_retries):
        try:
            # Add delay before API call to avoid rate limiting
            if attempt > 0:
                wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                print(f"  Retrying Gemini evaluation (attempt {attempt + 1}/{max_retries}) in {wait_time}s...")
                time.sleep(wait_time)

            contents = [prompt]
            for uf in uploaded_files:
                if uf:
                    contents.append(uf)

            response = model.generate_content(contents)

            # Parse response to get the best index
            text = response.text
            try:
                best_index = int(text.split()[0])
                if 0 <= best_index < len(images):
                    break  # Success!
                else:
                    best_index = 0
                    break
            except:
                best_index = 0
                break

        except Exception as e:
            if "500" in str(e) or "Internal" in str(e):
                if attempt < max_retries - 1:
                    print(f"  Gemini API error (500), will retry...")
                else:
                    print(f"  Gemini evaluation failed after {max_retries} attempts: {e}")
                    best_index = 0
            else:
                print(f"  Error during Gemini evaluation: {e}")
                best_index = 0
                break

    # Clean up uploaded files from Gemini
    for uf in uploaded_files:
        if uf:
            try:
                uf.delete()
            except Exception as e:
                print(f"  Warning: Failed to delete uploaded file: {e}")

    # Clean up local temp files
    for temp_file in temp_files:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

    # Add delay after evaluation to prevent rate limiting
    time.sleep(3)  # Increased from 1s to 3s

    return best_index

def main():
    # Load keywords from JSON
    with open('keywords.json', 'r', encoding='utf-8') as f:
        keywords_data = json.load(f)

    # Filter out invalid entries (like the header row)
    keywords_data = [k for k in keywords_data if k['id'] not in ['编号', '']]

    output_dir = 'output'
    os.makedirs(output_dir, exist_ok=True)

    # Configuration from environment variables
    use_gemini_eval = os.environ.get('USE_GEMINI_EVAL', 'false').lower() == 'true'
    img_size = os.environ.get('IMG_SIZE', 'xlarge')  # huge, icon, large, medium, small, xlarge, xxlarge
    img_type = os.environ.get('IMG_TYPE', 'photo')  # clipart, face, lineart, photo, animated
    img_color_type = os.environ.get('IMG_COLOR_TYPE', None)  # color, gray, mono, trans
    img_dominant_color = os.environ.get('IMG_DOMINANT_COLOR', None)  # black, blue, brown, etc.
    file_type = os.environ.get('FILE_TYPE', None)  # jpg, gif, png, bmp, svg, webp, ico
    num_results = int(os.environ.get('NUM_RESULTS', '5'))  # Number of search results (max 10)

    # Keyword range configuration
    start_index = int(os.environ.get('START_INDEX', '0'))  # Starting keyword index
    end_index = int(os.environ.get('END_INDEX', '30'))  # Ending keyword index (exclusive)

    print(f"Search Configuration:")
    print(f"  - Image Size: {img_size}")
    print(f"  - Image Type: {img_type}")
    print(f"  - Number of Results: {num_results}")
    if img_color_type:
        print(f"  - Color Type: {img_color_type}")
    if img_dominant_color:
        print(f"  - Dominant Color: {img_dominant_color}")
    if file_type:
        print(f"  - File Type: {file_type}")
    print(f"  - Gemini Evaluation: {use_gemini_eval}")
    print(f"  - Processing Keywords: {start_index} to {end_index}\n")

    processed_count = 0
    for index, item in enumerate(keywords_data[start_index:end_index], start=start_index):
        keyword = item['keyword_formatted']

        # Check if image already exists
        filename = os.path.join(output_dir, f"{item['id']}_{keyword.replace(' ', '_')}.jpg")
        if os.path.exists(filename):
            print(f"Skipping [{item['id']}]: {keyword} (already exists)")
            continue

        print(f"Processing keyword [{item['id']}]: {keyword}")
        images = search_images(
            keyword,
            num=num_results,
            img_size=img_size,
            img_type=img_type,
            img_color_type=img_color_type,
            img_dominant_color=img_dominant_color,
            file_type=file_type,
            exclude_watermark=True
        )
        if not images:
            print("  No images found")
            continue

        # Choose best image
        if use_gemini_eval:
            print("  Using Gemini to evaluate best image...")
            best_index = evaluate_best_image(images, keyword)
        else:
            print("  Selecting first image (Gemini evaluation disabled)...")
            best_index = 0

        # Try to download the best image, with fallback to other images if it fails
        downloaded = False
        attempts = min(3, len(images))  # Try up to 3 images

        for try_index in range(attempts):
            if try_index > 0:
                print(f"  Trying alternative image (#{try_index + 1})...")

            img_to_try = images[(best_index + try_index) % len(images)]
            url = img_to_try.get('original', img_to_try.get('link', ''))

            if download_image(url, filename):
                # Verify the downloaded image
                try:
                    file_size = os.path.getsize(filename)
                    if file_size < 1024:
                        print(f"  ⚠ Downloaded file too small ({file_size} bytes), trying next...")
                        os.remove(filename)
                        continue

                    # Quick validation: check if file can be opened as image
                    with Image.open(filename) as img:
                        img.verify()  # Verify it's a valid image

                    print(f"  ✓ Saved {filename} ({file_size // 1024}KB)")
                    downloaded = True
                    break
                except Exception as e:
                    print(f"  ⚠ Downloaded file is corrupted ({e}), trying next...")
                    if os.path.exists(filename):
                        os.remove(filename)
                    continue

        if not downloaded:
            print(f"  ✗ Failed to download after {attempts} attempts")
        else:
            processed_count += 1

        # Add cooldown period every 10 processed keywords to prevent rate limiting
        if use_gemini_eval and processed_count > 0 and processed_count % 10 == 0:
            print(f"\n⏸️  Cooldown period: waiting 30 seconds to avoid rate limits...")
            time.sleep(30)
            print("✓ Resuming processing\n")

if __name__ == "__main__":
    main()