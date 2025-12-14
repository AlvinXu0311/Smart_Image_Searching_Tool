#!/usr/bin/env python3
"""
Detect and remove corrupted images (HTML error pages, too small files)
"""
import os
import json
from pathlib import Path

def check_image_validity(filepath):
    """Check if file is a valid image"""
    if not os.path.exists(filepath):
        return False, "File not found"

    file_size = os.path.getsize(filepath)

    # Check if file is too small (likely an error page)
    if file_size < 1024:  # Less than 1KB
        return False, f"File too small ({file_size} bytes)"

    # Check if file starts with valid JPEG magic bytes
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            # JPEG files start with FF D8 FF
            if not (header[0:2] == b'\xff\xd8'):
                return False, f"Invalid JPEG header (starts with {header[:10].hex()})"
    except Exception as e:
        return False, f"Error reading file: {e}"

    return True, "OK"

def main():
    output_dir = Path('output')
    if not output_dir.exists():
        print("Output directory not found!")
        return

    # Load keywords to get expected filenames
    with open('keywords.json', 'r', encoding='utf-8') as f:
        keywords_data = json.load(f)

    keywords_data = [k for k in keywords_data if k['id'] not in ['编号', '']]

    corrupted_files = []
    valid_files = []
    missing_files = []

    print("Checking all downloaded images...\n")

    for item in keywords_data:
        keyword = item['keyword_formatted']
        filename = output_dir / f"{item['id']}_{keyword.replace(' ', '_')}.jpg"

        if not filename.exists():
            missing_files.append((item['id'], keyword))
            continue

        is_valid, reason = check_image_validity(filename)

        if is_valid:
            valid_files.append((item['id'], keyword, filename))
            print(f"✓ [{item['id']}] {filename.name}")
        else:
            corrupted_files.append((item['id'], keyword, filename, reason))
            print(f"✗ [{item['id']}] {filename.name} - {reason}")

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Valid images:     {len(valid_files)}")
    print(f"  Corrupted images: {len(corrupted_files)}")
    print(f"  Missing images:   {len(missing_files)}")
    print(f"{'='*60}\n")

    if corrupted_files:
        print("Corrupted images found:")
        for id, keyword, filepath, reason in corrupted_files:
            print(f"  [{id}] {filepath.name}")
            print(f"      Reason: {reason}")

        response = input("\nDo you want to delete these corrupted files? (y/n): ")
        if response.lower() == 'y':
            for id, keyword, filepath, reason in corrupted_files:
                try:
                    os.remove(filepath)
                    print(f"  Deleted: {filepath.name}")
                except Exception as e:
                    print(f"  Error deleting {filepath.name}: {e}")
            print("\n✓ Corrupted files deleted. Run image_tool.py again to re-download them.")

    if missing_files:
        print("\nMissing images:")
        for id, keyword in missing_files:
            print(f"  [{id}] {keyword}")

if __name__ == "__main__":
    main()
