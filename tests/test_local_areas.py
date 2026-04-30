"""Tests for multiple local areas configuration."""

import pytest

from photo_analyzer.config import Settings


class TestLocalAreasParsing:
    """Test LOCAL_N_* configuration parsing."""

    def test_no_local_areas_configured(self):
        """Empty list when no LOCAL_* fields set."""
        settings = Settings(
            local_0_lat=None,
            local_0_lon=None,
            local_0_radius=None,
            local_1_lat=None,
            local_1_lon=None,
            local_1_radius=None,
            local_2_lat=None,
            local_2_lon=None,
            local_2_radius=None,
            local_3_lat=None,
            local_3_lon=None,
            local_3_radius=None,
            local_4_lat=None,
            local_4_lon=None,
            local_4_radius=None,
        )
        assert settings.local_areas == []

    def test_single_local_area(self):
        """Parse single LOCAL_0_* configuration."""
        # Set all LOCAL_* fields explicitly to override .env values
        settings = Settings(
            selection_mode="date",
            image_dirs_str="./photos",
            local_0_lat=22.543096,
            local_0_lon=114.057865,
            local_0_radius=60.0,
            local_1_lat=None,
            local_1_lon=None,
            local_1_radius=None,
            local_2_lat=None,
            local_2_lon=None,
            local_2_radius=None,
            local_3_lat=None,
            local_3_lon=None,
            local_3_radius=None,
            local_4_lat=None,
            local_4_lon=None,
            local_4_radius=None,
        )

        areas = settings.local_areas

        assert len(areas) == 1
        assert areas[0] == (22.543096, 114.057865, 60.0)

    def test_multiple_local_areas(self):
        """Parse multiple LOCAL_N_* configurations."""
        settings = Settings(
            local_0_lat=22.54,
            local_0_lon=114.06,
            local_0_radius=60.0,
            local_1_lat=39.90,
            local_1_lon=116.40,
            local_1_radius=30.0,
        )

        areas = settings.local_areas

        assert len(areas) == 2
        assert areas[0] == (22.54, 114.06, 60.0)
        assert areas[1] == (39.90, 116.40, 30.0)

    def test_non_contiguous_indices_work(self):
        """LOCAL_0 and LOCAL_2 both valid even without LOCAL_1."""
        # Set all LOCAL_* fields explicitly to override .env values
        settings = Settings(
            selection_mode="date",
            image_dirs_str="./photos",
            local_0_lat=22.54,
            local_0_lon=114.06,
            local_0_radius=60.0,
            local_1_lat=None,
            local_1_lon=None,
            local_1_radius=None,
            local_2_lat=39.90,
            local_2_lon=116.40,
            local_2_radius=30.0,
            local_3_lat=None,
            local_3_lon=None,
            local_3_radius=None,
            local_4_lat=None,
            local_4_lon=None,
            local_4_radius=None,
        )

        areas = settings.local_areas

        # Both areas are included (LOCAL_1 is just None, skipped)
        assert len(areas) == 2
        assert areas[0] == (22.54, 114.06, 60.0)
        assert areas[1] == (39.90, 116.40, 30.0)


class TestInLocalArea:
    """Test in_local_area function."""

    def test_no_gps_returns_false(self):
        """Photos without GPS are not in local area."""
        from photo_analyzer.__main__ import in_local_area

        local_areas = [(22.54, 114.06, 60.0)]
        assert in_local_area(None, 114.06, local_areas) is False
        assert in_local_area(22.54, None, local_areas) is False

    def test_within_single_area(self):
        """Photo within a local area returns True."""
        from photo_analyzer.__main__ import in_local_area

        local_areas = [(22.54, 114.06, 60.0)]
        # Same coordinates as center
        assert in_local_area(22.54, 114.06, local_areas) is True
        # Within radius (Shenzhen to Hong Kong ~30km)
        assert in_local_area(22.30, 114.17, local_areas) is True

    def test_outside_all_areas(self):
        """Photo outside all local areas returns False."""
        from photo_analyzer.__main__ import in_local_area

        local_areas = [(22.54, 114.06, 60.0)]  # Shenzhen
        # Beijing is ~1900km from Shenzhen
        assert in_local_area(39.90, 116.40, local_areas) is False

    def test_within_second_area(self):
        """Photo within any local area returns True."""
        from photo_analyzer.__main__ import in_local_area

        local_areas = [
            (22.54, 114.06, 60.0),  # Shenzhen
            (39.90, 116.40, 30.0),  # Beijing
        ]
        # Within Beijing area
        assert in_local_area(39.92, 116.40, local_areas) is True

    def test_empty_local_areas_returns_false(self):
        """No local areas means no photo is 'local'."""
        from photo_analyzer.__main__ import in_local_area

        assert in_local_area(22.54, 114.06, []) is False
