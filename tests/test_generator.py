import os
import pandas as pd
import pytest
from generate import generate_fire_arc_svg, parse_hull_tens, format_cell, resource_path


class TestFireArcSvg:
    def test_empty_or_none(self):
        assert generate_fire_arc_svg("") == ""
        assert generate_fire_arc_svg(None) == ""
        assert generate_fire_arc_svg("-") == ""

    def test_single_arcs(self):
        for arc in ["Fore", "Aft", "Port", "Starboard"]:
            svg = generate_fire_arc_svg(arc)
            assert "<svg" in svg
            assert 'fill="#571314"' in svg
            assert '<polygon points="10,42.5 40,32.5 40,52.5" fill="black" />' in svg

    def test_all_arcs(self):
        svg = generate_fire_arc_svg("Fore, Aft, Port, Starboard")
        assert '<circle cx="100.0" cy="42.5" r="40.0" fill="#571314" />' in svg

    def test_combined_arcs(self):
        svg = generate_fire_arc_svg("Fore, Port, Starboard")
        assert "<svg" in svg
        assert 'fill="#571314"' in svg

    def test_case_and_whitespace_insensitivity(self):
        svg1 = generate_fire_arc_svg("Fore, Port")
        svg2 = generate_fire_arc_svg("  fore ,  PORT ")
        assert svg1 == svg2

    def test_typo_tolerance_startboard(self):
        svg_corrected = generate_fire_arc_svg("Aft, Port, Starboard")
        svg_typo = generate_fire_arc_svg("Aft, Port, Startboard")
        assert svg_corrected == svg_typo


class TestHullTensParsing:
    def test_standard_hull(self):
        assert parse_hull_tens("72/24") == 7
        assert parse_hull_tens("15/5") == 1
        assert parse_hull_tens("100/33") == 10

    def test_low_hull_returns_zero(self):
        assert parse_hull_tens("4/1") == 0
        assert parse_hull_tens("6/2") == 0
        assert parse_hull_tens("9/3") == 0

    def test_invalid_and_null_inputs(self):
        assert parse_hull_tens(None) == 0
        assert parse_hull_tens("") == 0
        assert parse_hull_tens("invalid") == 0
        assert parse_hull_tens(float("nan")) == 0


class TestFormatCell:
    def test_valid_text(self):
        assert format_cell("Battleship") == "Battleship"

    def test_null_or_nan(self):
        assert format_cell(None) == "-"
        assert format_cell(float("nan")) == "-"
        assert format_cell("nan") == "-"
        assert format_cell("") == "-"

    def test_html_escaping(self):
        assert format_cell('4"') == "4&quot;"
        assert format_cell("A & B") == "A &amp; B"
        assert format_cell("<DP>") == "&lt;DP&gt;"


class TestCsvIntegrity:
    @pytest.fixture
    def ships_df(self):
        assert os.path.exists("ships.csv"), "ships.csv must exist"
        return pd.read_csv("ships.csv")

    @pytest.fixture
    def weapons_df(self):
        assert os.path.exists("weapon_systems.csv"), "weapon_systems.csv must exist"
        return pd.read_csv("weapon_systems.csv")

    def test_csv_columns(self, ships_df, weapons_df):
        required_ship_cols = {"ship_id", "ship_name", "ship_type", "points", "flank_speed", "armour", "hull"}
        assert required_ship_cols.issubset(set(ships_df.columns))

        required_weapon_cols = {"ship_id", "weapon_system", "fire_arc"}
        assert required_weapon_cols.issubset(set(weapons_df.columns))

    def test_weapon_ship_ids_match(self, ships_df, weapons_df):
        ship_ids = set(ships_df["ship_id"])
        weapon_ship_ids = set(weapons_df["ship_id"])
        assert weapon_ship_ids.issubset(ship_ids), "All weapons must reference existing ship IDs"

    def test_fire_arcs_valid(self, weapons_df):
        for _, row in weapons_df.iterrows():
            arc = row["fire_arc"]
            if pd.notna(arc) and str(arc).strip() != "-":
                svg = generate_fire_arc_svg(str(arc))
                assert svg != "", f"Fire arc '{arc}' for weapon '{row['weapon_system']}' could not be generated"


class TestPathSanitization:
    def test_sanitize_path_segment(self):
        from generate import sanitize_path_segment
        assert sanitize_path_segment("Normal Name") == "Normal_Name"
        assert sanitize_path_segment("Name / With / Slashes") == "Name_With_Slashes"
        assert sanitize_path_segment('Name "With" Quotes') == "Name_With_Quotes"
        assert sanitize_path_segment("Leading and Trailing. ") == "Leading_and_Trailing"
        assert sanitize_path_segment("Multiple    Spaces") == "Multiple_Spaces"


class TestComputeCardPaths:
    def test_default_group_by_type(self):
        from generate import compute_card_paths
        df = pd.DataFrame([
            {
                "ship_id": 1,
                "ship_name": "Bismarck",
                "ship_type": "Battleship",
                "nation_name": "Germany",
                "points": 450,
            },
            {
                "ship_id": 2,
                "ship_name": "Iowa",
                "ship_type": "Battleship",
                "nation_name": "United States",
                "points": 850,
            },
            {
                "ship_id": 3,
                "ship_name": "Enterprise",
                "ship_type": "Carrier",
                "nation_name": "United States",
                "points": 400,
            },
        ])
        paths = compute_card_paths(df, "output_images")
        assert paths[1] == os.path.join("output_images", "Germany", "Battleship", "Bismarck.png")
        assert paths[2] == os.path.join("output_images", "United_States", "Battleship", "Iowa.png")
        assert paths[3] == os.path.join("output_images", "United_States", "Aircraft_Carrier", "Enterprise.png")

    def test_explicit_group_by_class(self):
        from generate import compute_card_paths
        df = pd.DataFrame([
            {
                "ship_id": 1,
                "ship_name": "Bismarck",
                "ship_class": "Bismarck",
                "nation_name": "Germany",
                "points": 450,
            },
            {
                "ship_id": 2,
                "ship_name": "Iowa",
                "ship_class": "Iowa",
                "nation_name": "United States",
                "points": 850,
            },
        ])
        paths = compute_card_paths(df, "output_images", group_by="class")
        assert paths[1] == os.path.join("output_images", "Germany", "Bismarck", "Bismarck.png")
        assert paths[2] == os.path.join("output_images", "United_States", "Iowa", "Iowa.png")

    def test_duplicate_name_disambiguation(self):
        from generate import compute_card_paths
        df = pd.DataFrame([
            {
                "ship_id": 10,
                "ship_name": "Colorado (1944)",
                "ship_type": "Battleship",
                "nation_name": "United States",
                "points": 485,
            },
            {
                "ship_id": 11,
                "ship_name": "Colorado (1944)",
                "ship_type": "Battleship",
                "nation_name": "United States",
                "points": 505,
            },
        ])
        paths = compute_card_paths(df, "output_images")
        assert paths[10] == os.path.join("output_images", "United_States", "Battleship", "Colorado_(1944)_485pts.png")
        assert paths[11] == os.path.join("output_images", "United_States", "Battleship", "Colorado_(1944)_505pts.png")

    def test_flat_mode(self):
        from generate import compute_card_paths
        df = pd.DataFrame([
            {
                "ship_id": 1,
                "ship_name": "Bismarck",
                "ship_type": "Battleship",
                "nation_name": "Germany",
                "points": 450,
            }
        ])
        paths = compute_card_paths(df, "output_images", group_by="none")
        assert paths[1] == os.path.join("output_images", "Bismarck.png")

    def test_fallback_nation_flag(self):
        from generate import compute_card_paths
        df = pd.DataFrame([
            {
                "ship_id": 1,
                "ship_name": "Hood",
                "nation": "royal_navy_ensign.png",
                "ship_type": "Battlecruiser",
                "points": 350,
            }
        ])
        paths = compute_card_paths(df, "output_images")
        assert paths[1] == os.path.join("output_images", "Great_Britain", "Battlecruiser", "Hood.png")


