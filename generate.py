import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from string import Template
import os 
from PIL import Image, ImageDraw, ImageFont

# Input CSV and template paths
ships_csv = "ships.csv"
weapons_csv = "weapon_systems.csv"
template_file = "shipcard.html"
output_dir = "output_images"
os.makedirs(output_dir, exist_ok=True)

# Load the CSV files
ships = pd.read_csv(ships_csv)
weapons = pd.read_csv(weapons_csv)

# Load the HTML template
with open(template_file, "r") as file:
    html_template = Template(file.read())

# Configure Selenium WebDriver
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=options)

def draw_vertical_lines(image_path, num_top_lines):
    """
    Draw vertical lines at the top and bottom of the image based on the 300 DPI setting.
    The number of top lines is dynamic based on the ship's hull value.
    Add numbers at the end of those lines with a slight gap.
    Ensure the final image dimensions match the target size.
    """
    # Target dimensions (in pixels at 300 DPI)
    target_width = 1654
    target_height = 1289
    dpi = 300

    # Open the image
    with Image.open(image_path) as img:
        draw = ImageDraw.Draw(img)

        # Convert dimensions from mm to pixels at 300 DPI
        mm_to_inches = 25.4  # 1 inch = 25.4 mm
        px_per_mm = dpi / mm_to_inches  # Pixels per mm

        # Parameters for the lines
        top_start_x = 5 * px_per_mm  # 5mm from the left edge
        line_height = 3 * px_per_mm  # 5mm tall
        line_spacing = 10 * px_per_mm  # 10mm apart
        gap = 2 * px_per_mm  # Gap between the line and the numbers (2mm)

        # Font for numbers
        font_size = int(2.25 * px_per_mm)  # Font size is 2.25mm
        font = ImageFont.truetype("./fonts/dejavu/DejaVuSans.ttf", font_size)

        # Dynamically calculate the top numbers based on num_top_lines
        top_numbers = [i * 10 for i in range(1, num_top_lines + 1)]
        for i in range(num_top_lines):
            x = top_start_x + i * line_spacing
            draw.line([(x, 0), (x, line_height)], fill="#571314", width=3)
            # Draw the number with a gap below the line
            text = str(top_numbers[i])
            text_width, text_height = draw.textsize(text, font=font)
            draw.text((x - text_width / 2, line_height + gap), text, fill="black", font=font)

        # Draw 10 lines at the bottom with numbers
        num_bottom_lines = 10
        bottom_numbers = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        bottom_y_start = img.height - line_height  # Starting Y position for bottom lines
        for i in range(num_bottom_lines):
            x = top_start_x + i * line_spacing
            draw.line([(x, bottom_y_start), (x, img.height)], fill="#571314", width=2)
            # Draw the number with a gap above the line
            text = str(bottom_numbers[i])
            text_width, text_height = draw.textsize(text, font=font)
            draw.text((x - text_width / 2, bottom_y_start - text_height - gap), text, fill="black", font=font)

        # Explicitly resize to ensure correct dimensions
        img = img.resize((target_width, target_height), Image.ANTIALIAS)

        # Save the updated image with 300 DPI
        img.save(image_path, dpi=(dpi, dpi))

# Generate an image for each ship
for _, ship in ships.iterrows():
    # Filter weapon systems for the current ship
    ship_weapons = weapons[weapons["ship_id"] == ship["ship_id"]]

    # Generate weapon rows as HTML
    weapon_rows_html = ""
    for _, weapon in ship_weapons.iterrows():
        # Handle empty values for 'ad', 'ap', and 'dd' by replacing them with dashes
        ad = weapon['ad'] if pd.notna(weapon['ad']) else "-"
        ap = weapon['ap'] if pd.notna(weapon['ap']) else "-"
        dd = weapon['dd'] if pd.notna(weapon['dd']) else "-"

        # Ensure 'traits' is handled correctly
        traits = weapon['traits'] if pd.notna(weapon['traits']) else "-"

        # Generate the row
        weapon_rows_html += f"""
        <tr>
            <td>{weapon['weapon_system']}</td>
            <td>{weapon['fire_arc']}</td>
            <td>{weapon['point_blank']}</td>
            <td>{weapon['short']}</td>
            <td>{weapon['long']}</td>
            <td>{weapon['extreme']}</td>
            <td>{ad}</td>
            <td>{ap}</td>
            <td>{dd}</td>
            <td>{traits}</td>
        </tr>
        """

    # Extract the first number from the hull (e.g., "72/24" -> 7)
    num_top_lines = int(str(ship["hull"]).split("/")[0][0])

    # Validate and handle missing ship/nation images
    ship_image_html = ""
    if not pd.isna(ship["ship_image"]) and isinstance(ship["ship_image"], str) and os.path.exists("ship_images/" + ship["ship_image"]):
        print("Ship image found:", ship["ship_image"])
        ship_image_html = f'<img class="ship-image" src="ship_images/{ship["ship_image"]}" alt="{ship["ship_name"]}" />'

    nation_html = ""
    if not pd.isna(ship["nation"]) and isinstance(ship["nation"], str) and os.path.exists("flags/" + ship["nation"]):
        print("Nation image found:", ship["nation"])
        nation_html = f'<img class="flag" src="flags/{ship["nation"]}" alt="Flag" />'

    # Replace placeholders in the template with ship and weapon data
    html_content = html_template.substitute(
        base_dir=os.getcwd(),
        ship_name=ship["ship_name"].upper(),
        ship_type=ship["ship_type"].upper(),
        points=ship["points"],
        ship_image_html=ship_image_html,  # Insert the generated ship image HTML
        nation_html=nation_html,  # Insert the generated nation flag HTML
        flank_speed=ship["flank_speed"],
        armour=ship["armour"],
        hull=ship["hull"],
        traits=ship["traits"],
        weapon_rows=weapon_rows_html
    )

    # Save the dynamic HTML to a unique file
    temp_html_path = os.path.join(output_dir, f"temp_{ship['ship_id']}.html")
    with open(temp_html_path, "w") as temp_file:
        temp_file.write(html_content)

    # Open the temporary HTML file in the browser
    driver.get(f"file://{os.path.abspath(temp_html_path)}?cache-bust={os.urandom(8).hex()}")

    # Inject CSS to hide scrollbars
    driver.execute_script("""
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.overflow = 'hidden';
        document.documentElement.style.margin = '0';
        document.documentElement.style.padding = '0';
        document.documentElement.style.overflow = 'hidden';
    """)

    # Wait for the page to load fully
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "table"))
    )

    # Force fixed dimensions for 14 cm × 10.9 cm at 300 DPI
    output_width = 1653  # 14 cm
    output_height = 1288  # 10.9 cm
    driver.set_window_size(output_width, output_height)

    # Capture the screenshot
    screenshot_path = os.path.join(output_dir, f"{ship['ship_name'].replace(' ', '_')}.png")
    print(f"Saving screenshot to: {screenshot_path}")
    driver.save_screenshot(screenshot_path)

    # Save the image with 300 DPI and draw vertical lines
    with Image.open(screenshot_path) as img:
        img.save(screenshot_path, dpi=(300, 300))

    # Add vertical lines after ensuring the image has been saved at 300 DPI
    draw_vertical_lines(screenshot_path, num_top_lines)

    # Clean up the temporary HTML file
    os.remove(temp_html_path)

# Cleanup
driver.quit()
print(f"Images saved in '{output_dir}'")
