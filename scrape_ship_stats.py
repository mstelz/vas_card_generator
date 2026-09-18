#!/usr/bin/env python3
"""
scrape_ship_stats.py

Extracts ship statistics and weapon systems for all ships.
Generates:
- ships.csv: Complete database of ships, stats, points, traits, silhouettes, and flags.
- weapon_systems.csv: Complete database of all weapon systems, fire arcs, range bands, and traits.
"""

import argparse
import concurrent.futures
import csv
import html
import os
import re
import sys
import urllib.request
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

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

NATION_FLAGS = {
    "uk": "royal_navy_ensign.png",
    "us": "usa.png",
    "japan": "japan.png",
    "germany": "kriegsmarine_ensign.png",
    "italy": "italian_ensign.png",
    "france": "french_ensign.png",
    "netherlands": "netherlands.png",
}

ARC_MAP = {
    "all.png": "Fore, Aft, Port, Starboard",
    "f270.png": "Fore, Port, Starboard",
    "r270.png": "Aft, Port, Starboard",
    "ps90.png": "Port, Starboard",
    "f90.png": "Fore",
    "p90.png": "Port",
    "s90.png": "Starboard",
}


def fetch_text(url: str, timeout: int = 15) -> str:
    """Fetch text content from a URL."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Warning: Failed to fetch {url}: {e}", file=sys.stderr)
        return ""


def clean_trait_text(text: str) -> List[str]:
    """Clean multi-space separated trait strings."""
    if not text:
        return []
    parts = re.split(r' {2,}|\t+|\n+', text)
    cleaned = []
    for p in parts:
        p = p.strip()
        if p and p not in ["--", "None", "-"]:
            cleaned.append(p)
    return cleaned


def parse_ship_page(url: str, nation_code: str, default_image: str) -> Optional[dict]:
    """Fetch and parse a ship details page."""
    page_html = fetch_text(url)
    if not page_html:
        return None

    # Ship Name
    name_m = re.search(r'<strong>([^<]+)</strong>', page_html)
    ship_name = name_m.group(1).strip() if name_m else "Unknown"

    def get_field(k: str) -> str:
        m = re.search(rf'<strong>{k}:</strong></td><td[^>]*>([^<]*)', page_html, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    # Points [WLPS]
    pts_m = re.search(r'<strong>Cost \[WLPS\]:</strong></td><td[^>]*>([^<]*)', page_html, re.IGNORECASE)
    if not pts_m:
        pts_m = re.search(r'<b>(\d+)</b>\s*Points', page_html, re.IGNORECASE)
    pts = pts_m.group(1).replace("Points", "").strip() if pts_m else "0"

    speed = get_field("Flank Speed")
    armor = get_field("Armor")
    hull = get_field("Hull").replace(" ", "")
    traits_raw = get_field("Traits")
    aircraft = get_field("Aircraft")
    tb = get_field("Torpedo Belt")
    stype = get_field("Type")

    # Normalize ship type
    stype_lower = stype.lower()
    if "carrier" in stype_lower:
        stype = "Carrier"
    elif "battleship" in stype_lower:
        stype = "Battleship"
    elif "cruiser" in stype_lower:
        stype = "Cruiser"
    elif "destroyer" in stype_lower:
        stype = "Destroyer"
    elif "sub" in stype_lower:
        stype = "Submarine"
    elif "civilian" in stype_lower or "merchant" in stype_lower:
        stype = "Civilian"

    # Assemble traits list
    traits_list = []
    if aircraft and aircraft not in ["0", "None", "--"]:
        traits_list.append(f"Aircraft {aircraft}")
    if tb and tb.lower() not in ["none", "--", "0"]:
        traits_list.append(f"Torpedo Belt {tb}")
    for t in clean_trait_text(traits_raw):
        if t not in traits_list:
            traits_list.append(t)
    traits_str = ", ".join(traits_list)

    # Format speed with inches quotes
    speed_formatted = speed
    if speed and not speed.endswith('"'):
        speed_formatted = f'{speed}"'

    # Extract ship image from page if present, else fallback to default_image
    img_m = re.search(r'/(?:img/[^/]+/)?([^"\' >/]+\.(?:png|jpg|gif))', page_html)
    if img_m:
        raw_img = img_m.group(1)
        if raw_img.endswith("_thumb.png"):
            image_filename = raw_img[:-10] + ".png"
        else:
            image_filename = raw_img
    else:
        image_filename = default_image

    flag_file = NATION_FLAGS.get(nation_code, "")
    if stype == "Civilian" and not flag_file:
        flag_file = ""

    # Weapons parsing
    weapons = []
    weapon_section = re.search(r'<strong>Weapons</strong>(.*?)</table>', page_html, re.DOTALL)
    if weapon_section:
        rows = re.findall(r'<tr>(.*?)</tr>', weapon_section.group(1), re.DOTALL)
        for r in rows:
            cols = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
            clean_cols = [re.sub(r'<[^>]+>', ' ', c).strip() for c in cols]
            if not clean_cols or len(clean_cols) < 5:
                continue

            w_name = clean_cols[0]
            arc_m = re.search(r'src=["\']?/img/arcs/([^\'">]+)', r)
            arc_img = arc_m.group(1) if arc_m else ""
            fire_arc = ARC_MAP.get(arc_img, "Fore, Aft, Port, Starboard")

            range_val = clean_cols[2] if len(clean_cols) > 2 else ""
            r_parts = [p.strip() for p in range_val.split("/")]
            if len(r_parts) == 4:
                pb, sh, lo, ex = r_parts
            else:
                pb = sh = lo = ex = "-"

            def fmt_range(v: str) -> str:
                v = v.replace('--"', '-').replace('--', '-').strip()
                if not v or v == "-":
                    return "-"
                if not v.endswith('"'):
                    return f'{v}"'
                return v

            pb, sh, lo, ex = fmt_range(pb), fmt_range(sh), fmt_range(lo), fmt_range(ex)
            ad = clean_cols[3].replace('--', '-').strip() if len(clean_cols) > 3 else "-"
            ap = clean_cols[4].replace('--', '-').strip() if len(clean_cols) > 4 else "-"
            dd = clean_cols[5].replace('--', '-').strip() if len(clean_cols) > 5 else "-"
            w_traits = clean_cols[6].replace('--', '-').strip() if len(clean_cols) > 6 else "-"
            if w_traits != "-":
                w_traits = ", ".join(clean_trait_text(w_traits))

            weapons.append({
                "weapon_system": w_name,
                "fire_arc": fire_arc,
                "point_blank": pb,
                "short": sh,
                "long": lo,
                "extreme": ex,
                "ad": ad,
                "ap": ap,
                "dd": dd,
                "traits": w_traits if w_traits else "-"
            })

    return {
        "ship_name": ship_name,
        "ship_type": stype,
        "points": pts,
        "flank_speed": f'{speed.rstrip("\"")}"' if speed else "",
        "armour": armor,
        "hull": hull,
        "traits": traits_str,
        "ship_image": image_filename,
        "nation": flag_file,
        "weapons": weapons,
    }


def discover_all_ship_links(base_url: str, nations: List[str]) -> List[dict]:
    """Scan all nation lists to get each ship's direct link and initial metadata."""
    discovered = []
    seen = set()

    for code in nations:
        nation_name = NATION_CODES.get(code, code.title())
        print(f"Scanning ships list for: {nation_name} ({code})...")
        for page in ["ships_list.php", "ships_class_list.php"]:
            url = urljoin(base_url, f"{page}?op=pick_nation&nation={code}") if base_url else ""
            if not url:
                continue
            page_html = fetch_text(url)
            if not page_html:
                continue

            matches = re.findall(
                r'<b>([^<]+)</b>\s*<br>\s*<a\s+href="([^"]*(displayShipData|displaySubData|displayMerchData)[^"]*unit=(\d+)[^"]*)[^>]*>\s*<img\s+src=[\'"]?([^\'">]+)[\'"]?>',
                page_html,
                re.IGNORECASE
            )

            for raw_name, link, op, unit_id, thumb_img in matches:
                name = raw_name.strip()
                unit_id = unit_id.strip()
                full_link = urljoin(base_url, f"ship_details.php?op={op}&unit={unit_id}") if base_url else ""

                thumb_filename = os.path.basename(thumb_img)
                if thumb_filename.endswith("_thumb.png"):
                    image_filename = thumb_filename[:-10] + ".png"
                else:
                    image_filename = thumb_filename

                key = (code, unit_id, name)
                if key not in seen:
                    seen.add(key)
                    discovered.append({
                        "nation_code": code,
                        "nation_name": nation_name,
                        "unit_id": unit_id,
                        "link": full_link,
                        "ship_name_hint": name,
                        "image_filename": image_filename,
                    })

    print(f"Discovered {len(discovered)} ship links across {len(nations)} nations.")
    return discovered


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape ship stats and weapons from remote source.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL for remote asset source")
    parser.add_argument("--ships-out", default="ships.csv", help="Output CSV for all ships (default: ships.csv)")
    parser.add_argument("--weapons-out", default="weapon_systems.csv", help="Output CSV for all weapons (default: weapon_systems.csv)")
    parser.add_argument("--nations", default="all", help="Comma-separated nations (default: all -> uk,us,france,netherlands,italy,germany,japan)")
    parser.add_argument("--workers", type=int, default=16, help="Concurrent workers (default: 16)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of ships to scrape (default: None, scrape all)")
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

    print("=== Victory at Sea Ship Stats & Weapons Scraper ===")
    print(f"Nations: {', '.join(nations)}")
    print(f"Workers: {args.workers}")

    # 1. Discover all links
    ship_items = discover_all_ship_links(args.base_url, nations)
    if args.limit:
        ship_items = ship_items[:args.limit]
        print(f"Limiting to first {len(ship_items)} ships...")

    # 2. Concurrently scrape each ship's details
    print(f"\nScraping {len(ship_items)} ship detail pages...")

    all_ships = []
    all_weapons = []
    ship_id_counter = 1

    def scrape_one(item):
        data = parse_ship_page(item["link"], item["nation_code"], item["image_filename"])
        if data:
            data["unit_id"] = item["unit_id"]
            data["nation_code"] = item["nation_code"]
        return item, data

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_item = {executor.submit(scrape_one, item): item for item in ship_items}
        total = len(future_to_item)

        for i, future in enumerate(concurrent.futures.as_completed(future_to_item), 1):
            item, data = future.result()
            if data:
                # We will assign sequential ship_id after gathering
                all_ships.append((item, data))
            if i % 100 == 0 or i == total:
                print(f"  Progress: {i}/{total} pages scraped ({len(all_ships)} succeeded)")

    # Sort deterministically by nation then unit_id
    all_ships.sort(key=lambda x: (x[0]["nation_code"], int(x[0]["unit_id"]) if x[0]["unit_id"].isdigit() else 0))

    # Write ships CSV and weapons CSV
    print(f"\nWriting {len(all_ships)} ships to {args.ships_out} and weapons to {args.weapons_out}...")

    with open(args.ships_out, "w", newline="", encoding="utf-8") as f_ships, \
         open(args.weapons_out, "w", newline="", encoding="utf-8") as f_weap:

        ship_writer = csv.writer(f_ships)
        ship_writer.writerow([
            "ship_id", "ship_name", "ship_type", "points", "flank_speed",
            "armour", "hull", "traits", "ship_image", "nation", "unit_id"
        ])

        weap_writer = csv.writer(f_weap)
        weap_writer.writerow([
            "ship_id", "weapon_system", "fire_arc", "point_blank", "short",
            "long", "extreme", "ad", "ap", "dd", "traits"
        ])

        for sid, (item, sdata) in enumerate(all_ships, start=1):
            ship_writer.writerow([
                sid,
                sdata["ship_name"],
                sdata["ship_type"],
                sdata["points"],
                sdata["flank_speed"],
                sdata["armour"],
                sdata["hull"],
                sdata["traits"],
                sdata["ship_image"],
                sdata["nation"],
                sdata["unit_id"],
            ])

            for w in sdata["weapons"]:
                weap_writer.writerow([
                    sid,
                    w["weapon_system"],
                    w["fire_arc"],
                    w["point_blank"],
                    w["short"],
                    w["long"],
                    w["extreme"],
                    w["ad"],
                    w["ap"],
                    w["dd"],
                    w["traits"],
                ])

    print(f"Successfully generated {args.ships_out} ({len(all_ships)} ships) and {args.weapons_out}!")


if __name__ == "__main__":
    main()
