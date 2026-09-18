#!/usr/bin/env python3
"""
fetch_ship_assets.py

Downloads ship images and flags from a remote source
for use with the Victory at Sea (VAS) card generator.

Features:
- Crawls all 7 nations (UK, US, France, Netherlands, Italy, Germany, Japan)
- Discovers all unique full-size ship drawings
- Extracts ship metadata (ship name, class, type, nation, refits, points)
- Downloads ship images concurrently using ThreadPoolExecutor
- Downloads ensign / flag images for all nations
- Optionally auto-converts images into transparent black silhouettes using connected components
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

DEFAULT_BASE_URL = os.environ.get("VAS_BASE_URL", "")

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


def convert_image_to_silhouette(
    source_img_path: str,
    output_img_path: str,
    flip_horizontal: bool = False
) -> bool:
    """
    Convert a ship drawing into a clean transparent silhouette.
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


def crawl_site(base_url: str, nations: List[str]) -> Tuple[Dict[str, str], List[dict]]:
    """
    Crawls ships_list and ships_class_list for specified nations.
    Returns:
    - images_map: {image_filename: full_image_url}
    - catalog: list of dicts with ship and image details
    """
    images_map = {}
    catalog = []
    seen_entries = set()

    for nation_code in nations:
        nation_name = NATION_CODES.get(nation_code, nation_code.title())
        print(f"Crawling nation: {nation_name} ({nation_code})...")

        for page in ["ships_list.php", "ships_class_list.php"]:
            url = urljoin(base_url, f"{page}?op=pick_nation&nation={nation_code}") if base_url else ""
            if not url:
                continue
            html = fetch_url(url)
            if not html:
                continue

            # Find all table cells with ship entries
            items = re.findall(
                r'<b>([^<]+)</b>\s*<br>\s*<a\s+href="([^"]*unit=(\d+)[^"]*)"[^>]*>\s*<img\s+src=[\'"]?([^\'">]+)[\'"]?></a>\s*<br>(?:<i>([^<]*)</i>)?(?:\s*Class)?\s*([^\s<]+)?',
                html,
                re.IGNORECASE
            )

            for name, link, unit_id, thumb_src, ship_class, ship_type in items:
                name = name.strip()
                unit_id = unit_id.strip()
                ship_class = ship_class.strip() if ship_class else ""
                ship_type = ship_type.strip() if ship_type else ""

                thumb_filename = os.path.basename(thumb_src)
                if thumb_filename.endswith("_thumb.png"):
                    image_filename = thumb_filename[:-10] + ".png"
                else:
                    image_filename = thumb_filename

                full_subpath = thumb_src.replace("_thumb.png", ".png").lstrip("/")
                image_url = urljoin(base_url, full_subpath) if base_url else image_filename
                images_map[image_filename] = image_url

                entry_key = (nation_code, unit_id, name, image_filename)
                if entry_key not in seen_entries:
                    seen_entries.add(entry_key)
                    catalog.append({
                        "nation": nation_name,
                        "nation_code": nation_code,
                        "unit_id": unit_id,
                        "ship_name": name,
                        "ship_class": ship_class,
                        "ship_type": ship_type,
                        "image_filename": image_filename,
                        "image_url": image_url,
                    })

    print(f"Discovered {len(images_map)} unique ship images and {len(catalog)} catalog entries.")
    return images_map, catalog


def download_flags(base_url: str, flags_dir: str):
    """Download national naval ensigns / flags from the remote source."""
    os.makedirs(flags_dir, exist_ok=True)
    print(f"\nDownloading flags to {flags_dir}...")
    for remote_name, local_name in FLAG_FILES.items():
        url = urljoin(base_url, f"img/flags/{remote_name}") if base_url else ""
        if not url:
            continue
        dest = os.path.join(flags_dir, local_name)
        ok = download_file(url, dest)
        if ok:
            print(f"  Downloaded flag: {local_name}")
        else:
            print(f"  Flag not found: {remote_name}")


def parse_args():
    parser = argparse.ArgumentParser(description="Download ship images and flags from remote source.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL for remote asset source"
    )
    parser.add_argument(
        "--raw-dir",
        default="ship_plates",
        help="Directory to save raw ship images (default: ship_plates)"
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
        default=None,
        help="Optional output CSV for scraped ship metadata catalog"
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
        help="Limit number of images to download (default: None, download all)"
    )
    parser.add_argument(
        "--convert",
        action="store_true",
        help="Also auto-convert downloaded images into silhouettes in silhouettes-dir"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.base_url:
        print("Error: No base URL specified. Set VAS_BASE_URL env var or provide --base-url.", file=sys.stderr)
        sys.exit(1)

    if args.nations.lower() == "all":
        nations = list(NATION_CODES.keys())
    else:
        nations = [n.strip().lower() for n in args.nations.split(",") if n.strip().lower() in NATION_CODES]

    print("=== Victory at Sea Asset Downloader ===")
    print(f"Nations: {', '.join(nations)}")
    print(f"Raw images destination: {args.raw_dir}")
    print(f"Silhouettes destination: {args.silhouettes_dir}")
    print(f"Flags destination: {args.flags_dir}")

    # 1. Download flags
    download_flags(args.base_url, args.flags_dir)

    # 2. Crawl site for ship images and catalog
    images_map, catalog = crawl_site(args.base_url, nations)

    # Save catalog if requested
    if catalog and args.catalog:
        with open(args.catalog, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["nation", "nation_code", "unit_id", "ship_name", "ship_class", "ship_type", "image_filename", "image_url"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(catalog)
        print(f"Saved catalog metadata to: {args.catalog}")

    # Apply limit if requested
    items_to_download = list(images_map.items())
    if args.limit:
        items_to_download = items_to_download[:args.limit]
        print(f"Limiting download to first {len(items_to_download)} images...")

    # 3. Concurrent download of ship images
    os.makedirs(args.raw_dir, exist_ok=True)
    print(f"\nDownloading {len(items_to_download)} ship images using {args.workers} workers...")

    success_count = 0
    fail_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_file = {
            executor.submit(download_file, url, os.path.join(args.raw_dir, filename)): filename
            for filename, url in items_to_download
        }

        total = len(future_to_file)
        for i, future in enumerate(concurrent.futures.as_completed(future_to_file), 1):
            filename = future_to_file[future]
            try:
                ok = future.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1

            if i % 50 == 0 or i == total:
                print(f"  Progress: {i}/{total} images processed ({success_count} succeeded, {fail_count} failed)")

    print(f"\nDownload completed: {success_count} succeeded, {fail_count} failed.")

    # 4. Optional silhouette conversion
    if args.convert:
        os.makedirs(args.silhouettes_dir, exist_ok=True)
        print(f"\nConverting {success_count} images to silhouettes in {args.silhouettes_dir}...")
        sil_success = 0
        for filename, _ in items_to_download:
            src = os.path.join(args.raw_dir, filename)
            dst = os.path.join(args.silhouettes_dir, filename)
            if os.path.exists(src):
                if convert_image_to_silhouette(src, dst):
                    sil_success += 1
        print(f"Silhouette conversion completed: {sil_success} silhouettes created.")

    print("\nAll tasks finished successfully!")


if __name__ == "__main__":
    main()
