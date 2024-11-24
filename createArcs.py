import os
from PIL import Image, ImageDraw

# Define fire arc combinations
fire_arcs = [
    "Fore",
    "Fore, Port",
    "Fore, Port, Starboard",
    "Fore, Starboard",
    "Port",
    "Fore, Aft, Port, Starboard",
    "Aft",
    "Aft, Port",
    "Aft, Port, Starboard",
    "Aft, Starboard",
    "Starboard"
]

output_dir = "fire_arcs"
os.makedirs(output_dir, exist_ok=True)

def standardize_fire_arc(fire_arc):
    """
    Standardize fire arc input by trimming whitespace,
    converting to lowercase, and sorting components for consistency.
    """
    if not fire_arc:
        return None
    # Split, standardize, and sort
    return "_".join(sorted(part.strip().lower() for part in fire_arc.split(",")))

def create_arc_image(arcs, output_path):
    """
    Create an arc image based on the given arcs.
    """
    # Image dimensions
    width, height = 100, 85
    center = (width // 2, height // 2)
    radius = 40

    # Arc angles
    arc_angles = {
        "Fore": (45, 135),
        "Port": (135, 225),
        "Aft": (225, 315),
        "Starboard": (315, 45)
    }

    # Create a blank image
    img = Image.new("RGBA", (width + 50, height), (255, 255, 255, 0))  # +50 for the arrow
    draw = ImageDraw.Draw(img)

    # Draw the arcs
    for arc in arcs:
        if arc in arc_angles:
            start, end = arc_angles[arc]
            draw.pieslice(
                [center[0] - radius + 50, center[1] - radius,  # +50 for the arrow
                 center[0] + radius + 50, center[1] + radius],  # +50 for the arrow
                start=start, end=end,
                fill=(139, 0, 0, 200)  # Dark red fill
            )

    # Draw the thin black border around the circle
    border_thickness = 1  # Thickness of the border
    draw.ellipse(
        [center[0] - radius + 50, center[1] - radius,  # +50 for the arrow
         center[0] + radius + 50, center[1] + radius],  # +50 for the arrow
        outline="black",
        width=border_thickness
    )

    # Draw the arrow
    arrow_base_y = 100 // 2
    arrow_coords = [
        (10, arrow_base_y),  # Arrow tip
        (40, arrow_base_y - 10),  # Upper base
        (40, arrow_base_y + 10)  # Lower base
    ]
    draw.polygon(arrow_coords, fill="black")

    # Save the image
    img.save(output_path)

# Generate images for all fire arc combinations
for fire_arc in fire_arcs:
    standardized_name = standardize_fire_arc(fire_arc)
    output_path = os.path.join(output_dir, f"{standardized_name}.png")
    arcs = fire_arc.split(", ")
    create_arc_image(arcs, output_path)
    print(f"Created: {output_path}")
