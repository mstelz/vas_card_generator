#!/usr/bin/env python3
"""
fetch_ship_assets.py

Scrapes and downloads ship plate images and flags from https://www.vas-admiralty-rules.com/
for use with the Victory at Sea (VAS) card generator.

Features:
- Crawls all 7 nations (UK, US, France, Netherlands, Italy, Germany, Japan)
- Discovers all unique full-size ship plate drawings (/img/ship_plates/<name>.png)
- Extracts ship metadata (ship name, class, type, nation, refits, points) into a catalog CSV
- Downloads ship plates concurrently using ThreadPoolExecutor
- Downloads ensign / flag images for all nations
- Optionally auto-converts plates into transparent black silhouettes using connected components
"""

import argparse
import concurrent.futures
import csv
import os
import re
import sys
import urllib.request
import urllib.error
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin

import numpy as np
from PIL import Image
from scipy.ndimage import label

BASE_URL = "https://www.vas-admiralty-rules.com/"

NATION_CODES = {
    "uk": "Great Britain",
    "us": "United States",
    "france": "France",
    "netherlands": "The Netherlands",
    "italy": "Italy",
    "germany": "Germany",
    "japan": "Japan",
}

FLAG_FILES = {
    "royal_navy_ensign.png": "royal_navy_ensign.png",
    "royal_navy_ensign_thumb.png": "royal_navy_ensign_thumb.png",
    "usn_ensign.png": "usn_ensign.png",
    "netherlands.png": "netherlands.png",
    "french_ensign_thumb.png": "french_ensign.png",
    "italian_ensign_thumb.png": "italian_ensign.png",
    "kriegsmarine_ensign_thumb.png": "kriegsmarine_ensign.png",
    "japanese_ensign_thumb.png": "japanese_ensign.png",
}


def fetch_url(url: str, headers: dict = None, timeout: int = 15) -> str:
    """Fetch text content from a URL with browser User-Agent."""
    req_headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Warning: Failed to fetch {url}: {e}", file=sys.stderr)
        return ""


def download_file(url: str, dest_path: str, timeout: int = 20) -> bool:
    """Download binary file from URL to destination path."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        return True  # Already downloaded

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if len(data) == 0:
                return False
            os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(data)
            return True
    except Exception as e:
        print(f"Warning: Failed to download {url} -> {dest_path}: {e}", file=sys.stderr)
        return False


def convert_plate_to_silhouette(
    source_img_path: str,
    output_img_path: str,
    flip_horizontal: bool = False
) -> bool:
    """
    Convert a Shipbucket-style ship plate image into a clean transparent silhouette.
    Uses connected-component analysis to isolate the ship hull/superstructure and discard
    the scale bar, measurement text ('50m', '100m'), and title/credits.
    """
    try:
        with Image.open(source_img_path) as img:
            rgba_img = img.convert("RGBA")
        arr = np.array(rgba_img)

        # Shipbucket background is white/near-white
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        is_foreground = ~((r > 240) & (g > 240) & (b > 240))

        # 8-connectivity labeling
        structure = np.ones((3, 3), dtype=int)
        labeled_array, num_features = label(is_foreground, structure=structure)

        if num_features == 0:
            return False

        # Find largest component (which is the ship)
        counts = np.bincount(labeled_array.ravel())
        counts[0] = 0  # ignore background
        ship_label = int(np.argmax(counts))

        # Find bounding box of main ship
        ship_ys, ship_xs = np.where(labeled_array == ship_label)
        if len(ship_ys) == 0:
            return False

        ship_min_y, ship_max_y = ship_ys.min(), ship_ys.max()
        ship_min_x, ship_max_x = ship_xs.min(), ship_xs.max()

        # Ship mask initially with main component
        ship_mask = (labeled_array == ship_label)

        # Include smaller components that are part of the ship (e.g. floatplanes, rigging, mast tops)
        # but exclude the scale bar and title text which are located near the top
        for comp_lbl in range(1, num_features + 1):
            if comp_lbl == ship_label:
                continue
            c_ys, c_xs = np.where(labeled_array == comp_lbl)
            if len(c_ys) == 0:
                continue
            c_min_y, c_max_y = c_ys.min(), c_ys.max()
            c_min_x, c_max_x = c_xs.min(), c_xs.max()
            c_width = c_max_x - c_min_x + 1
            c_height = c_max_y - c_min_y + 1

            # Discard top scale bar: wide horizontal bar near top (y <= 35)
            if c_min_y <= 25 and c_width > 150 and c_height < 25:
                continue
            # Discard text labels, credits, and scale numbers in the upper portion
            if c_max_y <= 35 and counts[comp_lbl] < 350:
                continue
            # Discard anything strictly outside the horizontal span of the ship with buffer
            if c_max_x < ship_min_x - 10 or c_min_x > ship_max_x + 10:
                continue

            # If it's vertically close to or within the ship bounds, include it
            if c_min_y >= ship_min_y - 10 and c_max_y <= ship_max_y + 5:
                ship_mask |= (labeled_array == comp_lbl)

        # Create RGBA silhouette
        sil_arr = np.zeros_like(arr)
        sil_arr[ship_mask, 3] = 255  # Solid alpha
        sil_arr[ship_mask, :3] = 0   # Black

        out_img = Image.fromarray(sil_arr, mode="RGBA")
        bbox = out_img.getbbox()
        if bbox:
            out_img = out_img.crop(bbox)

        if flip_horizontal:
            out_img = out_img.transpose(Image.FLIP_LEFT_RIGHT)

        os.makedirs(os.path.dirname(os.path.abspath(output_img_path)), exist_ok=True)
        out_img.save(output_img_path, "PNG")
        return True
    except Exception as e:
        print(f"Warning: Failed to convert {source_img_path} to silhouette: {e}", file=sys.stderr)
        return False


def crawl_site(nations: List[str]) -> Tuple[Dict[str, str], List[dict]]:
    """
    Crawls ships_list and ships_class_list for specified nations.
    Returns:
    - plates_map: {plate_filename: full_image_url}
    - catalog: list of dicts with ship and plate details
    """
    plates_map = {}
    catalog = []
    seen_entries = set()

    for nation_code in nations:
        nation_name = NATION_CODES.get(nation_code, nation_code.title())
        print(f"Crawling nation: {nation_name} ({nation_code})...")

        for page in ["ships_list.php", "ships_class_list.php"]:
            url = f"{BASE_URL}{page}?op=pick_nation&nation={nation_code}"
            html = fetch_url(url)
            if not html:
                continue

            # Find all table cells with ship entries
            # Pattern: <b>Ship Name</b><br><a href="...unit=(\d+)..."><img src=/img/ship_plates/([^>]+)></a><br><i>Class</i> Class Type
            # Let's use regex to capture ship items
            items = re.findall(
                r'<b>([^<]+)</b>\s*<br>\s*<a\s+href="([^"]*unit=(\d+)[^"]*)"[^>]*>\s*<img\s+src=[\'"]?/img/ship_plates/([^\'">]+)[\'"]?></a>\s*<br>(?:<i>([^<]*)</i>)?(?:\s*Class)?\s*([^\s<]+)?',
                html,
                re.IGNORECASE
            )

            for name, link, unit_id, thumb_img, ship_class, ship_type in items:
                name = name.strip()
                unit_id = unit_id.strip()
                ship_class = ship_class.strip() if ship_class else ""
                ship_type = ship_type.strip() if ship_type else ""

                # Full plate image name (remove _thumb if present)
                if thumb_img.endswith("_thumb.png"):
                    plate_filename = thumb_img[:-10] + ".png"
                else:
                    plate_filename = thumb_img

                plate_url = f"{BASE_URL}img/ship_plates/{plate_filename}"
                plates_map[plate_filename] = plate_url

                entry_key = (nation_code, unit_id, name, plate_filename)
                if entry_key not in seen_entries:
                    seen_entries.add(entry_key)
                    catalog.append({
                        "nation": nation_name,
                        "nation_code": nation_code,
                        "unit_id": unit_id,
                        "ship_name": name,
                        "ship_class": ship_class,
                        "ship_type": ship_type,
                        "plate_filename": plate_filename,
                        "plate_url": plate_url,
                    })

    print(f"Discovered {len(plates_map)} unique ship plates and {len(catalog)} catalog entries.")
    return plates_map, catalog


def download_flags(flags_dir: str):
    """Download national naval ensigns / flags from the site."""
    os.makedirs(flags_dir, exist_ok=True)
    print(f"\nDownloading flags to {flags_dir}...")
    for remote_name, local_name in FLAG_FILES.items():
        url = f"{BASE_URL}img/flags/{remote_name}"
        dest = os.path.join(flags_dir, local_name)
        ok = download_file(url, dest)
        if ok:
            print(f"  Downloaded flag: {local_name}")
        else:
            print(f"  Flag not found: {remote_name}")


def parse_args():
    parser = argparse.ArgumentParser(description="Download ship images and flags from vas-admiralty-rules.com.")
    parser.add_argument(
        "--plates-dir",
        default="ship_plates",
        help="Directory to save raw ship plate images (default: ship_plates)"
    )
    parser.add_argument(
        "--silhouettes-dir",
        default="ship_images",
        help="Directory to save converted silhouettes (default: ship_images)"
    )
    parser.add_argument(
        "--flags-dir",
        default="flags",
        help="Directory to save flags (default: flags)"
    )
    parser.add_argument(
        "--catalog",
        default="ship_catalog.csv",
        help="Output CSV for scraped ship metadata catalog (default: ship_catalog.csv)"
    )
    parser.add_argument(
        "--nations",
        default="all",
        help="Comma-separated nations to fetch (default: all -> uk,us,france,netherlands,italy,germany,japan)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Number of concurrent download threads (default: 12)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of plates to download (default: None, download all)"
    )
    parser.add_argument(
        "--convert",
        action="store_true",
        help="Also auto-convert downloaded plates into silhouettes in silhouettes-dir"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.nations.lower() == "all":
        nations = list(NATION_CODES.keys())
    else:
        nations = [n.strip().lower() for n in args.nations.split(",") if n.strip().lower() in NATION_CODES]

    print("=== Victory at Sea Asset Scraper & Downloader ===")
    print(f"Nations: {', '.join(nations)}")
    print(f"Plates destination: {args.plates_dir}")
    print(f"Silhouettes destination: {args.silhouettes_dir}")
    print(f"Flags destination: {args.flags_dir}")

    # 1. Download flags
    download_flags(args.flags_dir)

    # 2. Crawl site for ship plates and catalog
    plates_map, catalog = crawl_site(nations)

    # Save catalog
    if catalog and args.catalog:
        with open(args.catalog, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["nation", "nation_code", "unit_id", "ship_name", "ship_class", "ship_type", "plate_filename", "plate_url"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(catalog)
        print(f"Saved catalog metadata to: {args.catalog}")

    # Apply limit if requested
    items_to_download = list(plates_map.items())
    if args.limit:
        items_to_download = items_to_download[:args.limit]
        print(f"Limiting download to first {len(items_to_download)} plates...")

    # 3. Concurrent download of ship plates
    os.makedirs(args.plates_dir, exist_ok=True)
    print(f"\nDownloading {len(items_to_download)} ship plates using {args.workers} workers...")

    success_count = 0
    fail_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_plate = {
            executor.submit(download_file, url, os.path.join(args.plates_dir, filename)): filename
            for filename, url in items_to_download
        }

        total = len(future_to_plate)
        for i, future in enumerate(concurrent.futures.as_completed(future_to_plate), 1):
            filename = future_to_plate[future]
            try:
                ok = future.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1

            if i % 50 == 0 or i == total:
                print(f"  Progress: {i}/{total} plates processed ({success_count} succeeded, {fail_count} failed)")

    print(f"\nDownload completed: {success_count} succeeded, {fail_count} failed.")

    # 4. Optional silhouette conversion
    if args.convert:
        os.makedirs(args.silhouettes_dir, exist_ok=True)
        print(f"\nConverting {success_count} plates to silhouettes in {args.silhouettes_dir}...")
        sil_success = 0
        for filename, _ in items_to_download:
            src = os.path.join(args.plates_dir, filename)
            dst = os.path.join(args.silhouettes_dir, filename)
            if os.path.exists(src):
                if convert_plate_to_silhouette(src, dst):
                    sil_success += 1
        print(f"Silhouette conversion completed: {sil_success} silhouettes created.")

    print("\nAll tasks finished successfully!")


if __name__ == "__main__":
    main()
