import json
import os
import requests
import time
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

# Load environment variables from .env file
load_dotenv()

# Set up API keys
GOOGLE_CUSTOM_API_KEY = os.environ.get('GOOGLE_CUSTOM_API_KEY')
GOOGLE_CX = os.environ.get('GOOGLE_CX')

if not all([GOOGLE_CUSTOM_API_KEY, GOOGLE_CX]):
    raise ValueError("Please set GOOGLE_CUSTOM_API_KEY and GOOGLE_CX in the .env file")

def search_images(keyword, num=5, img_size='huge', img_type='photo',
                  img_color_type=None, img_dominant_color=None, file_type=None,
                  exclude_watermark=True, date_restrict=None, sort_by_date=False):
    """
    Search for images using Google Custom Search API
    Supports fetching more than 10 images through pagination

    Args:
        date_restrict: Restrict results to a time period
            - Format: d[number] (days), w[number] (weeks), m[number] (months), y[number] (years)
            - Examples: 'd7' (last 7 days), 'm6' (last 6 months), 'y1' (last year)
        sort_by_date: Sort results by date (newest first)
    """
    url = "https://www.googleapis.com/customsearch/v1"

    # Add exclusion terms for watermarked images
    search_query = keyword
    if exclude_watermark:
        search_query = f'{keyword} -watermark -"stock photo" -shutterstock -getty -istockphoto -alamy'

    all_images = []

    # Calculate how many requests we need (max 10 per request)
    max_total = min(num, 100)
    requests_needed = (max_total + 9) // 10

    for request_index in range(requests_needed):
        start_index = request_index * 10 + 1
        results_needed = min(10, max_total - len(all_images))

        if results_needed <= 0:
            break

        params = {
            "key": GOOGLE_CUSTOM_API_KEY,
            "cx": GOOGLE_CX,
            "q": search_query,
            "searchType": "image",
            "num": results_needed,
            "start": start_index,
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
        if date_restrict:
            params["dateRestrict"] = date_restrict
        if sort_by_date:
            params["sort"] = "date"

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            results = response.json()

            items = results.get('items', [])

            if not items:
                break

            for item in items:
                all_images.append({
                    'original': item.get('link'),
                    'link': item.get('link'),
                    'thumbnail': item.get('image', {}).get('thumbnailLink'),
                    'title': item.get('title'),
                    'source': item.get('displayLink')
                })

            # Small delay between requests
            if request_index < requests_needed - 1 and items:
                time.sleep(0.3)

        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Error fetching page {request_index + 1}: {e}")
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
                if len(content) < 1024:
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

                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA', 'P'):
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

def main():
    # Load keywords from JSON
    with open('keywords.json', 'r', encoding='utf-8') as f:
        keywords_data = json.load(f)

    # Filter out invalid entries
    keywords_data = [k for k in keywords_data if k['id'] not in ['编号', '']]

    output_candidates_dir = 'output_candidates'
    os.makedirs(output_candidates_dir, exist_ok=True)

    # Configuration from environment variables
    img_size = os.environ.get('IMG_SIZE', 'xlarge')
    img_type = os.environ.get('IMG_TYPE', 'photo')
    img_color_type = os.environ.get('IMG_COLOR_TYPE', None)
    img_dominant_color = os.environ.get('IMG_DOMINANT_COLOR', None)
    file_type = os.environ.get('FILE_TYPE', None)
    num_results = int(os.environ.get('NUM_RESULTS', '5'))
    date_restrict = os.environ.get('DATE_RESTRICT', None)
    sort_by_date = os.environ.get('SORT_BY_DATE', 'false').lower() == 'true'

    # Keyword range configuration
    process_ids_str = os.environ.get('PROCESS_IDS', None)
    process_parts_str = os.environ.get('PROCESS_PARTS', None)

    # Filter keywords based on configuration
    if process_ids_str:
        selected_ids = set()
        for id_spec in process_ids_str.split(','):
            id_spec = id_spec.strip()
            if ':' in id_spec:
                start_id, end_id = id_spec.split(':')
                start_part, start_num = map(int, start_id.split('-'))
                end_part, end_num = map(int, end_id.split('-'))

                if start_part != end_part:
                    print(f"Warning: Range {id_spec} spans multiple parts, skipping")
                    continue

                for num in range(start_num, end_num + 1):
                    selected_ids.add(f"{start_part}-{num}")
            else:
                selected_ids.add(id_spec)

        filtered_keywords = [k for k in keywords_data if k['id'] in selected_ids]
        range_desc = f"IDs: {process_ids_str}"

    elif process_parts_str:
        parts = [p.strip() for p in process_parts_str.split(',')]
        filtered_keywords = [k for k in keywords_data if k['id'].split('-')[0] in parts]
        range_desc = f"Parts: {process_parts_str}"

    else:
        start_index = int(os.environ.get('START_INDEX', '0'))
        end_index = int(os.environ.get('END_INDEX', str(len(keywords_data))))
        filtered_keywords = keywords_data[start_index:end_index]
        range_desc = f"Index {start_index} to {end_index}"

    print(f"Download Configuration:")
    print(f"  - Image Size: {img_size}")
    print(f"  - Image Type: {img_type}")
    print(f"  - Number of Results: {num_results}")
    if img_color_type:
        print(f"  - Color Type: {img_color_type}")
    if img_dominant_color:
        print(f"  - Dominant Color: {img_dominant_color}")
    if file_type:
        print(f"  - File Type: {file_type}")
    if date_restrict:
        print(f"  - Date Restrict: {date_restrict}")
    if sort_by_date:
        print(f"  - Sort By Date: Enabled (newest first)")
    print(f"  - Processing: {range_desc} ({len(filtered_keywords)} keywords)")
    print(f"  - Output: All candidates → 'output_candidates/'\n")

    for item in filtered_keywords:
        keyword = item['keyword_formatted']
        keyword_id = item['id']

        # Create folder for candidates
        keyword_folder = os.path.join(output_candidates_dir, f"{keyword_id}_{keyword.replace(' ', '_')}")

        # Check if folder already exists and has images
        if os.path.exists(keyword_folder):
            existing_images = [f for f in os.listdir(keyword_folder) if f.endswith('.jpg')]
            if len(existing_images) >= num_results:
                print(f"Skipping [{keyword_id}]: {keyword} (already has {len(existing_images)} images)")
                continue

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
            exclude_watermark=True,
            date_restrict=date_restrict,
            sort_by_date=sort_by_date
        )

        if not images:
            print("  No images found")
            continue

        print(f"  Found {len(images)} images, downloading all...")

        # Download all images to candidates folder
        downloaded_count = 0
        for img_index, img_data in enumerate(images):
            url = img_data.get('original', img_data.get('link', ''))
            candidate_filename = os.path.join(keyword_folder, f"candidate_{img_index + 1}.jpg")

            if download_image(url, candidate_filename):
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
                    downloaded_count += 1
                except Exception as e:
                    print(f"    ⚠ Candidate {img_index + 1} corrupted, skipped")
                    if os.path.exists(candidate_filename):
                        os.remove(candidate_filename)
                    continue
            else:
                print(f"    ✗ Failed to download candidate {img_index + 1}")

        if downloaded_count > 0:
            print(f"  ✓ Downloaded {downloaded_count}/{len(images)} images to: {keyword_folder}")
        else:
            print(f"  ✗ No images downloaded successfully")

if __name__ == "__main__":
    main()
