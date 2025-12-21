import json
import os
import time
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
import shutil

# Load environment variables from .env file
load_dotenv()

# Set up API key for Gemini
GOOGLE_AI_API_KEY = os.environ.get('GOOGLE_AI_API_KEY')

if not GOOGLE_AI_API_KEY:
    raise ValueError("Please set GOOGLE_AI_API_KEY in the .env file")

# Configure Gemini
genai.configure(api_key=GOOGLE_AI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

def evaluate_best_image(images_folder, keyword, keyword_id, max_retries=3):
    """Evaluate images using Gemini with retry logic"""
    # Find all candidate images
    candidate_files = sorted([
        f for f in os.listdir(images_folder)
        if f.startswith('candidate_') and f.endswith('.jpg')
    ])

    if not candidate_files:
        print(f"  ✗ No candidate images found in {images_folder}")
        return None

    print(f"  Found {len(candidate_files)} candidate images")

    # Prepare prompt
    prompt = f"Here are {len(candidate_files)} images searched for the keyword '{keyword}'. Which one is the best match? Choose the index (1 to {len(candidate_files)}) of the best image fitting the keyword without watermark. Just return the number."

    # Upload images to Gemini
    uploaded_files = []
    for candidate_file in candidate_files:
        file_path = os.path.join(images_folder, candidate_file)
        try:
            uploaded_file = genai.upload_file(file_path)
            uploaded_files.append(uploaded_file)
            time.sleep(0.5)
        except Exception as e:
            print(f"  ⚠ Failed to upload {candidate_file}: {e}")
            uploaded_files.append(None)

    # Add delay before generation
    time.sleep(2)

    # Generate content with retry logic
    best_index = 1  # Default to first image
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = 2 ** attempt
                print(f"  Retrying Gemini evaluation (attempt {attempt + 1}/{max_retries}) in {wait_time}s...")
                time.sleep(wait_time)

            contents = [prompt]
            for uf in uploaded_files:
                if uf:
                    contents.append(uf)

            response = model.generate_content(contents)

            # Parse response
            text = response.text.strip()
            print(f"  Gemini response: {text}")

            try:
                best_index = int(text.split()[0])
                if 1 <= best_index <= len(candidate_files):
                    break
                else:
                    print(f"  ⚠ Invalid index {best_index}, using first image")
                    best_index = 1
                    break
            except:
                print(f"  ⚠ Could not parse response, using first image")
                best_index = 1
                break

        except Exception as e:
            if "500" in str(e) or "Internal" in str(e):
                if attempt < max_retries - 1:
                    print(f"  Gemini API error (500), will retry...")
                else:
                    print(f"  Gemini evaluation failed after {max_retries} attempts: {e}")
                    best_index = 1
            else:
                print(f"  Error during Gemini evaluation: {e}")
                best_index = 1
                break

    # Clean up uploaded files from Gemini
    for uf in uploaded_files:
        if uf:
            try:
                uf.delete()
            except Exception as e:
                print(f"  Warning: Failed to delete uploaded file: {e}")

    # Add delay after evaluation
    time.sleep(3)

    # Return the filename of the best image
    if 1 <= best_index <= len(candidate_files):
        best_file = candidate_files[best_index - 1]
        return os.path.join(images_folder, best_file)
    else:
        return None

def main():
    # Load keywords from JSON
    with open('keywords.json', 'r', encoding='utf-8') as f:
        keywords_data = json.load(f)

    # Filter out invalid entries
    keywords_data = [k for k in keywords_data if k['id'] not in ['编号', '']]

    output_dir = 'output'
    output_candidates_dir = 'output_candidates'
    os.makedirs(output_dir, exist_ok=True)

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

    print(f"Evaluation Configuration:")
    print(f"  - Processing: {range_desc} ({len(filtered_keywords)} keywords)")
    print(f"  - Input: Candidates from 'output_candidates/'")
    print(f"  - Output: Best image → 'output/'\n")

    evaluated_count = 0
    for item in filtered_keywords:
        keyword = item['keyword_formatted']
        keyword_id = item['id']

        # Check if output image already exists
        final_filename = os.path.join(output_dir, f"{keyword_id}_{keyword.replace(' ', '_')}.jpg")
        if os.path.exists(final_filename):
            print(f"Skipping [{keyword_id}]: {keyword} (already exists in output)")
            continue

        # Find candidates folder
        keyword_folder = os.path.join(output_candidates_dir, f"{keyword_id}_{keyword.replace(' ', '_')}")

        if not os.path.exists(keyword_folder):
            print(f"Skipping [{keyword_id}]: {keyword} (no candidates folder found)")
            continue

        print(f"Evaluating keyword [{keyword_id}]: {keyword}")

        # Use Gemini to evaluate
        best_image_path = evaluate_best_image(keyword_folder, keyword, keyword_id)

        if best_image_path and os.path.exists(best_image_path):
            try:
                shutil.copy2(best_image_path, final_filename)
                print(f"  ✓ Best image copied to output: {final_filename}")
                evaluated_count += 1
            except Exception as e:
                print(f"  ✗ Failed to copy best image: {e}")
        else:
            print(f"  ✗ No valid best image found")

        # Cooldown every 10 evaluations
        if evaluated_count > 0 and evaluated_count % 10 == 0:
            print(f"\n⏸️  Cooldown period: waiting 30 seconds to avoid rate limits...")
            time.sleep(30)
            print("✓ Resuming evaluation\n")

    print(f"\n✓ Evaluation complete! Evaluated {evaluated_count} keywords.")

if __name__ == "__main__":
    main()
