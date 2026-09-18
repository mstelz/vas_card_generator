import argparse
import html
import math
import os
import sys
from string import Template
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def generate_fire_arc_svg(fire_arc_str: str, width: int = 45) -> str:
    """
    Generate an inline SVG string for a given fire arc combination.
    Visual styling matches createArcs.py:
    - Circle center (cx, cy) = (100, 42.5), radius = 40
    - ViewBox = "0 0 150 85"
    - Arrow on the left pointing left, vertically centered at y = 42.5
    - Arc wedges:
        * Fore: 315 deg to 45 deg (Right quadrant)
        * Port: 45 deg to 135 deg (Bottom quadrant)
        * Aft: 135 deg to 225 deg (Left quadrant)
        * Starboard: 225 deg to 315 deg (Top quadrant)
    - Fill color: #571314
    """
    if not fire_arc_str or not isinstance(fire_arc_str, str):
        return ""

    raw_parts = [p.strip().lower() for p in fire_arc_str.split(",") if p.strip()]
    parts = set()
    for p in raw_parts:
        if "startboard" in p:
            parts.add("starboard")
        else:
            parts.add(p)

    has_fore = "fore" in parts
    has_port = "port" in parts
    has_aft = "aft" in parts
    has_starboard = "starboard" in parts

    active_count = sum([has_fore, has_port, has_aft, has_starboard])
    if active_count == 0:
        return ""

    cx, cy = 100.0, 42.5
    r = 40.0
    d = r * math.cos(math.pi / 4.0)

    TR = f"{cx + d:.3f},{cy - d:.3f}"
    BR = f"{cx + d:.3f},{cy + d:.3f}"
    BL = f"{cx - d:.3f},{cy + d:.3f}"
    TL = f"{cx - d:.3f},{cy - d:.3f}"

    def arc_path(start_pt, end_pt, large_arc=0):
        return f'<path d="M {cx},{cy} L {start_pt} A {r} {r} 0 {large_arc} 1 {end_pt} Z" fill="#571314" />'

    paths = []

    if active_count == 4:
        paths.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#571314" />')
    elif active_count == 3:
        if not has_fore:
            paths.append(arc_path(BR, TR, large_arc=1))
        elif not has_port:
            paths.append(arc_path(BL, BR, large_arc=1))
        elif not has_aft:
            paths.append(arc_path(TL, BL, large_arc=1))
        elif not has_starboard:
            paths.append(arc_path(TR, TL, large_arc=1))
    elif active_count == 2:
        if has_fore and has_port:
            paths.append(arc_path(TR, BL, large_arc=0))
        elif has_port and has_aft:
            paths.append(arc_path(BR, TL, large_arc=0))
        elif has_aft and has_starboard:
            paths.append(arc_path(BL, TR, large_arc=0))
        elif has_starboard and has_fore:
            paths.append(arc_path(TL, BR, large_arc=0))
        elif has_fore and has_aft:
            paths.append(arc_path(TR, BR, large_arc=0))
            paths.append(arc_path(BL, TL, large_arc=0))
        elif has_port and has_starboard:
            paths.append(arc_path(BR, BL, large_arc=0))
            paths.append(arc_path(TL, TR, large_arc=0))
    elif active_count == 1:
        if has_fore:
            paths.append(arc_path(TR, BR, large_arc=0))
        elif has_port:
            paths.append(arc_path(BR, BL, large_arc=0))
        elif has_aft:
            paths.append(arc_path(BL, TL, large_arc=0))
        elif has_starboard:
            paths.append(arc_path(TL, TR, large_arc=0))

    paths_str = "\n    ".join(paths)
    outline = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="black" stroke-width="1" />'
    arrow = f'<polygon points="10,{cy} 40,{cy - 10} 40,{cy + 10}" fill="black" />'

    height = width * 85 / 150
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 150 85" width="{width}" height="{height:.1f}" style="display:inline-block; vertical-align:middle;">\n'
        f"    {paths_str}\n"
        f"    {outline}\n"
        f"    {arrow}\n"
        f"</svg>"
    )


def parse_hull_tens(hull_val) -> int:
    """Extract tens count for top calibration lines (e.g. '72/24' -> 7, '4/1' -> 0)."""
    try:
        if pd.isna(hull_val):
            return 0
        hull_str = str(hull_val).strip()
        total_hull = int(hull_str.split("/")[0].strip())
        return max(0, total_hull // 10)
    except (ValueError, IndexError):
        return 0


def format_cell(value, default: str = "-") -> str:
    """Safely format a table cell value, escaping HTML and replacing nulls with default."""
    if pd.isna(value):
        return default
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return default
    return html.escape(s)


def draw_vertical_lines(image_path: str, num_top_lines: int, font_path: str = None):
    """
    Draw calibration vertical lines at the top and bottom of the image for 300 DPI.
    Ensures exact 1654x1289 dimensions.
    """
    target_width = 1654
    target_height = 1289
    dpi = 300

    mm_to_inches = 25.4
    px_per_mm = dpi / mm_to_inches

    top_start_x = 5 * px_per_mm
    line_height = 3 * px_per_mm
    line_spacing = 10 * px_per_mm
    gap = 2 * px_per_mm

    font_size = int(2.25 * px_per_mm)
    if font_path and os.path.exists(font_path):
        font = ImageFont.truetype(font_path, font_size)
    else:
        fallback = resource_path(os.path.join("fonts", "DejaVuSans.ttf"))
        if os.path.exists(fallback):
            font = ImageFont.truetype(fallback, font_size)
        else:
            font = ImageFont.load_default()

    with Image.open(image_path) as img:
        # Resize to target dimensions FIRST if needed, so lines and numbers are drawn at 1:1 pixel perfection
        if img.size != (target_width, target_height):
            img = img.resize((target_width, target_height), Image.LANCZOS)

        draw = ImageDraw.Draw(img)

        # Draw top lines only when num_top_lines > 0 (for hull >= 10)
        if num_top_lines > 0:
            top_numbers = [i * 10 for i in range(1, num_top_lines + 1)]
            for i in range(num_top_lines):
                x = top_start_x + i * line_spacing
                draw.line([(x, 0), (x, line_height)], fill="#571314", width=3)
                text = str(top_numbers[i])
                text_width = draw.textlength(text, font=font)
                draw.text((x - text_width / 2, line_height + gap), text, fill="black", font=font)

        # Draw 10 lines at the bottom (0 through 9)
        num_bottom_lines = 10
        bottom_numbers = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        bottom_y_start = target_height - line_height
        for i in range(num_bottom_lines):
            x = top_start_x + i * line_spacing
            draw.line([(x, bottom_y_start), (x, target_height)], fill="#571314", width=2)
            text = str(bottom_numbers[i])
            text_width = draw.textlength(text, font=font)
            text_height = font.size if hasattr(font, "size") else int(font_size)
            draw.text((x - text_width / 2, bottom_y_start - text_height - gap), text, fill="black", font=font)

        img.save(image_path, dpi=(dpi, dpi))


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def check_setup(ships_csv: str, weapons_csv: str):
    required_files = [ships_csv, weapons_csv, "ship_images", "flags"]
    missing_items = [item for item in required_files if not os.path.exists(item)]
    if missing_items:
        print("Error: The following required files or directories are missing:")
        for item in missing_items:
            print(f"  - {item}")
        print("\nPlease ensure the directory structure matches the required format and includes the necessary files.")
        sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate Victory at Sea ship cards.")
    parser.add_argument("--ships-csv", default="ships.csv", help="Path to ships CSV (default: ships.csv)")
    parser.add_argument("--weapons-csv", default="weapon_systems.csv", help="Path to weapon systems CSV (default: weapon_systems.csv)")
    parser.add_argument("--template", default=None, help="Path to HTML template (default: shipcard.html)")
    parser.add_argument("--output-dir", default="output_images", help="Output directory (default: output_images)")
    parser.add_argument("--ship-id", default=None, help="Specific ship ID(s) to generate, comma-separated (e.g. --ship-id 2 or --ship-id 1,3)")
    return parser.parse_args()


def main():
    args = parse_args()
    check_setup(args.ships_csv, args.weapons_csv)

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    template_file = args.template if args.template else resource_path("shipcard.html")
    with open(template_file, "r") as f:
        html_template = Template(f.read())

    font_path = resource_path(os.path.join("fonts", "DejaVuSans.ttf"))

    ships = pd.read_csv(args.ships_csv)
    weapons = pd.read_csv(args.weapons_csv)

    # Filter by ship-id if specified
    if args.ship_id:
        target_ids = {int(x.strip()) for x in args.ship_id.split(",") if x.strip().isdigit()}
        ships = ships[ships["ship_id"].isin(target_ids)]
        if ships.empty:
            print(f"No ships found matching ID(s): {args.ship_id}")
            return

    driver = None
    try:
        driver = create_driver()
        output_width = 1654
        output_height = 1289
        driver.set_window_size(output_width, output_height)

        for _, ship in ships.iterrows():
            ship_id = ship["ship_id"]
            ship_name_raw = str(ship["ship_name"]).strip()
            print(f"Generating card for: {ship_name_raw} (ID: {ship_id})")

            ship_weapons = weapons[weapons["ship_id"] == ship_id]

            weapon_rows_html = ""
            for _, weapon in ship_weapons.iterrows():
                weapon_system = html.escape(str(weapon["weapon_system"]).strip())
                fire_arc_svg = generate_fire_arc_svg(str(weapon["fire_arc"]))
                point_blank = format_cell(weapon["point_blank"])
                short_val = format_cell(weapon["short"])
                long_val = format_cell(weapon["long"])
                extreme = format_cell(weapon["extreme"])
                ad = format_cell(weapon["ad"])
                ap = format_cell(weapon["ap"])
                dd = format_cell(weapon["dd"])
                traits = format_cell(weapon["traits"])

                weapon_rows_html += f"""
                <tr>
                    <td>{weapon_system}</td>
                    <td>{fire_arc_svg}</td>
                    <td>{point_blank}</td>
                    <td>{short_val}</td>
                    <td>{long_val}</td>
                    <td>{extreme}</td>
                    <td>{ad}</td>
                    <td>{ap}</td>
                    <td>{dd}</td>
                    <td>{traits}</td>
                </tr>
                """

            ship_image_html = ""
            if pd.notna(ship.get("ship_image")):
                img_name = str(ship["ship_image"]).strip()
                img_path = os.path.join("ship_images", img_name)
                if img_name and os.path.exists(img_path):
                    ship_image_html = f'<img class="ship-image" src="{img_path}" alt="{html.escape(ship_name_raw)}" />'

            nation_html = ""
            if pd.notna(ship.get("nation")):
                flag_name = str(ship["nation"]).strip()
                flag_path = os.path.join("flags", flag_name)
                if flag_name and os.path.exists(flag_path):
                    nation_html = f'<img class="flag" src="{flag_path}" alt="Flag" />'

            ship_name = html.escape(ship_name_raw.upper())
            ship_type = html.escape(str(ship["ship_type"]).strip().upper())
            points = html.escape(str(ship["points"]).strip())
            flank_speed = format_cell(ship["flank_speed"])
            armour = format_cell(ship["armour"])
            hull = format_cell(ship["hull"])
            ship_traits = format_cell(ship["traits"])

            html_content = html_template.substitute(
                base_dir=os.getcwd(),
                ship_name=ship_name,
                ship_type=ship_type,
                points=points,
                ship_image_html=ship_image_html,
                nation_html=nation_html,
                flank_speed=flank_speed,
                armour=armour,
                hull=hull,
                traits=ship_traits,
                weapon_rows=weapon_rows_html,
            )

            temp_html_path = os.path.join(output_dir, f"temp_{ship_id}.html")
            try:
                with open(temp_html_path, "w") as temp_file:
                    temp_file.write(html_content)

                driver.get(f"file://{os.path.abspath(temp_html_path)}?cache-bust={os.urandom(8).hex()}")

                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )

                safe_ship_name = ship_name_raw.replace(" ", "_")
                screenshot_path = os.path.join(output_dir, f"{safe_ship_name}.png")
                driver.save_screenshot(screenshot_path)

                top_tens = parse_hull_tens(ship["hull"])
                draw_vertical_lines(screenshot_path, top_tens, font_path=font_path)
            finally:
                if os.path.exists(temp_html_path):
                    os.remove(temp_html_path)

        print(f"Cards successfully generated and saved in '{output_dir}'")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
