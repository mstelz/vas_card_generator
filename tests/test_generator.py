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
