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
    Supports fetching more than 10 images through pagination

    Args:
        keyword: Search query
        num: Number of results (can be up to 100, uses pagination for >10)
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

    all_images = []

    # Calculate how many requests we need (max 10 per request)
    # Google allows up to 100 results total with pagination
    max_total = min(num, 100)
    requests_needed = (max_total + 9) // 10  # Round up division

    for request_index in range(requests_needed):
        start_index = request_index * 10 + 1  # Google uses 1-based indexing
        results_needed = min(10, max_total - len(all_images))

        if results_needed <= 0:
            break

        params = {
            "key": GOOGLE_CUSTOM_API_KEY,
            "cx": GOOGLE_CX,
            "q": search_query,
            "searchType": "image",
            "num": results_needed,
            "start": start_index,  # Pagination parameter
            "imgSize": img_size,
            "imgType": img_type,
            "safe": "off"
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
            items = results.get('items', [])

            if not items:
                # No more results available
                break

            for item in items:
                all_images.append({
                    'original': item.get('link'),
                    'link': item.get('link'),
                    'thumbnail': item.get('image', {}).get('thumbnailLink'),
                    'title': item.get('title'),
                    'source': item.get('displayLink')
                })

            # Small delay between requests to be respectful
            if request_index < requests_needed - 1 and items:
                time.sleep(0.3)

        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Error fetching page {request_index + 1}: {e}")
            # Continue with what we have
            break

    return all_images

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
    prompt = f"Here are {len(images)} images searched for the keyword '{keyword}'. Which one is the best match? Choose the index (0 to {len(images)-1}) of the best image fitting the keywor without watermark"

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
    output_candidates_dir = 'output_candidates'
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(output_candidates_dir, exist_ok=True)

    # Configuration from environment variables
    use_gemini_eval = os.environ.get('USE_GEMINI_EVAL', 'false').lower() == 'true'
    img_size = os.environ.get('IMG_SIZE', 'xlarge')  # huge, icon, large, medium, small, xlarge, xxlarge
    img_type = os.environ.get('IMG_TYPE', 'photo')  # clipart, face, lineart, photo, animated
    img_color_type = os.environ.get('IMG_COLOR_TYPE', None)  # color, gray, mono, trans
    img_dominant_color = os.environ.get('IMG_DOMINANT_COLOR', None)  # black, blue, brown, etc.
    file_type = os.environ.get('FILE_TYPE', None)  # jpg, gif, png, bmp, svg, webp, ico
    num_results = int(os.environ.get('NUM_RESULTS', '5'))  # Number of search results (max 10)

    # Keyword range configuration - supports multiple formats
    # Option 1: Index-based (old method): START_INDEX=0, END_INDEX=30
    # Option 2: ID-based: PROCESS_IDS=1-1,1-5,2-1:2-10 (specific IDs or ranges)
    # Option 3: Part-based: PROCESS_PARTS=1,2,3 (process entire parts)

    process_ids_str = os.environ.get('PROCESS_IDS', None)
    process_parts_str = os.environ.get('PROCESS_PARTS', None)

    # Filter keywords based on configuration
    if process_ids_str:
        # ID-based filtering (e.g., "1-1,1-5,2-1:2-10")
        selected_ids = set()
        for id_spec in process_ids_str.split(','):
            id_spec = id_spec.strip()
            if ':' in id_spec:
                # Range like "2-1:2-10"
                start_id, end_id = id_spec.split(':')
                start_part, start_num = map(int, start_id.split('-'))
                end_part, end_num = map(int, end_id.split('-'))

                if start_part != end_part:
                    print(f"Warning: Range {id_spec} spans multiple parts, skipping")
                    continue

                for num in range(start_num, end_num + 1):
                    selected_ids.add(f"{start_part}-{num}")
            else:
                # Single ID like "1-1"
                selected_ids.add(id_spec)

        filtered_keywords = [k for k in keywords_data if k['id'] in selected_ids]
        range_desc = f"IDs: {process_ids_str}"

    elif process_parts_str:
        # Part-based filtering (e.g., "1,2,3")
        parts = [p.strip() for p in process_parts_str.split(',')]
        filtered_keywords = [k for k in keywords_data if k['id'].split('-')[0] in parts]
        range_desc = f"Parts: {process_parts_str}"

    else:
        # Index-based filtering (old method, for backward compatibility)
        start_index = int(os.environ.get('START_INDEX', '0'))
        end_index = int(os.environ.get('END_INDEX', str(len(keywords_data))))
        filtered_keywords = keywords_data[start_index:end_index]
        range_desc = f"Index {start_index} to {end_index}"

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
    print(f"  - Processing: {range_desc} ({len(filtered_keywords)} keywords)")
    print(f"  - Output: Best image → 'output/', All candidates → 'output_candidates/'\n")

    processed_count = 0
    for item in filtered_keywords:
        keyword = item['keyword_formatted']
        keyword_id = item['id']

        # Check if image already exists in output
        final_filename = os.path.join(output_dir, f"{keyword_id}_{keyword.replace(' ', '_')}.jpg")
        if os.path.exists(final_filename):
            print(f"Skipping [{keyword_id}]: {keyword} (already exists in output)")
            continue

        # Create folder for candidates
        keyword_folder = os.path.join(output_candidates_dir, f"{keyword_id}_{keyword.replace(' ', '_')}")
        os.makedirs(keyword_folder, exist_ok=True)

        print(f"Processing keyword [{keyword_id}]: {keyword}")
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

        print(f"  Found {len(images)} images, downloading all...")

        # Download all images to candidates folder
        downloaded_images = []
        for img_index, img_data in enumerate(images):
            url = img_data.get('original', img_data.get('link', ''))

            # Save to candidates folder
            candidate_filename = os.path.join(keyword_folder, f"candidate_{img_index + 1}.jpg")

            if download_image(url, candidate_filename):
                # Verify the downloaded image
                try:
                    file_size = os.path.getsize(candidate_filename)
                    if file_size < 1024:
                        print(f"    ⚠ Candidate {img_index + 1} too small, skipped")
                        os.remove(candidate_filename)
                        continue

                    # Quick validation
                    with Image.open(candidate_filename) as img:
                        img.verify()

                    print(f"    ✓ Candidate {img_index + 1} saved ({file_size // 1024}KB)")
                    downloaded_images.append((img_index, candidate_filename))
                except Exception as e:
                    print(f"    ⚠ Candidate {img_index + 1} corrupted, skipped")
                    if os.path.exists(candidate_filename):
                        os.remove(candidate_filename)
                    continue
            else:
                print(f"    ✗ Failed to download candidate {img_index + 1}")

        if not downloaded_images:
            print(f"  ✗ No images downloaded successfully")
            continue

        # Copy best image to output folder
        best_downloaded = None
        for img_idx, filepath in downloaded_images:
            if img_idx == best_index:
                best_downloaded = filepath
                break

        # If best image failed, try fallback to other downloaded images
        if not best_downloaded and downloaded_images:
            best_downloaded = downloaded_images[0][1]
            print(f"  ⚠ Best image not available, using fallback")

        if best_downloaded:
            import shutil
            shutil.copy2(best_downloaded, final_filename)
            print(f"  ✓ Best image copied to output: {final_filename}")
            print(f"  ✓ All {len(downloaded_images)} candidates saved to: {keyword_folder}")
            processed_count += 1
        else:
            print(f"  ✗ Failed to save best image to output")

        # Add cooldown period every 10 processed keywords to prevent rate limiting
        if use_gemini_eval and processed_count > 0 and processed_count % 10 == 0:
            print(f"\n⏸️  Cooldown period: waiting 30 seconds to avoid rate limits...")
            time.sleep(30)
            print("✓ Resuming processing\n")

if __name__ == "__main__":
    main()