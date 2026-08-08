"""Tests for IS 4326:1993 seismic band design (lintel/roof bands in masonry)."""

import pytest
from iscodes.design.masonry_bands import design_seismic_band, BandResult


class TestLintelbandReinforcement:
    """Test reinforcement selection for lintel band at span <= 5m."""

    def test_zone_ii_span_le_5m(self):
        """Zone II, span <= 5m: 2 bars, 8mm dia."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert result.ok
        assert result.data["n_bars"] == 2
        assert result.data["bar_dia_mm"] == 8
        # Ast_prov = 2 * pi * 8^2 / 4 = 2 * pi * 16 = 32*pi ≈ 100.53
        assert abs(result.data["Ast_prov_mm2"] - 2 * 3.14159 * 16) < 1.0

    def test_zone_iii_span_le_5m(self):
        """Zone III, span <= 5m: 2 bars, 10mm dia."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=5.0,
            seismic_zone="III",
        )
        assert result.ok
        assert result.data["n_bars"] == 2
        assert result.data["bar_dia_mm"] == 10

    def test_zone_iv_span_le_5m(self):
        """Zone IV, span <= 5m: 2 bars, 12mm dia."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=3.0,
            seismic_zone="IV",
        )
        assert result.ok
        assert result.data["n_bars"] == 2
        assert result.data["bar_dia_mm"] == 12

    def test_zone_v_span_le_5m(self):
        """Zone V, span <= 5m: 2 bars, 12mm dia."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.0,
            seismic_zone="V",
        )
        assert result.ok
        assert result.data["n_bars"] == 2
        assert result.data["bar_dia_mm"] == 12


class TestLintelbandLargeSpan:
    """Test reinforcement selection for span > 5m."""

    def test_zone_iii_span_gt_5m(self):
        """Zone III, span > 5m: 2 bars, 12mm dia."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=6.0,
            seismic_zone="III",
        )
        assert result.ok
        assert result.data["n_bars"] == 2
        assert result.data["bar_dia_mm"] == 12

    def test_zone_v_span_gt_5m(self):
        """Zone V, span > 5m: 3 bars, 16mm dia."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=8.0,
            seismic_zone="V",
        )
        assert result.ok
        assert result.data["n_bars"] == 3
        assert result.data["bar_dia_mm"] == 16


class TestBandDepth:
    """Test band depth constraints."""

    def test_depth_below_minimum_floors_to_75(self):
        """Depth request below 75 mm should floor to 75 mm."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
            band_depth_mm=50,  # below minimum
        )
        assert result.ok
        assert result.data["depth_mm"] == 75  # floored to minimum

    def test_depth_at_minimum_75_unchanged(self):
        """Depth exactly at 75 mm should remain 75 mm."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
            band_depth_mm=75,
        )
        assert result.ok
        assert result.data["depth_mm"] == 75

    def test_depth_above_minimum_ceils_to_site_standard_25(self):
        """Depth above 75 mm should ceil to nearest multiple of 25."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
            band_depth_mm=76,  # above 75, not a multiple of 25
        )
        assert result.ok
        assert result.data["depth_mm"] == 100  # ceil to next multiple of 25

    def test_depth_none_defaults_to_75(self):
        """band_depth_mm=None should default to 75 mm."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
            band_depth_mm=None,
        )
        assert result.ok
        assert result.data["depth_mm"] == 75


class TestStirrupSpacing:
    """Test stirrup (transverse) reinforcement spacing."""

    def test_stirrup_spacing_multiple_of_25(self):
        """Stirrup spacing should be a multiple of 25 mm."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert result.ok
        assert result.data["stirrup_spacing_mm"] % 25.0 == 0

    def test_stirrup_spacing_not_exceeds_150(self):
        """Stirrup spacing should not exceed code max of 150 mm."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert result.ok
        assert result.data["stirrup_spacing_mm"] <= 150


class TestValidation:
    """Test error handling and validation."""

    def test_invalid_zone_raises_keyerror(self):
        """Invalid seismic zone should raise KeyError (matching codebase pattern)."""
        with pytest.raises(KeyError):
            design_seismic_band(
                band_type="lintel",
                wall_thickness_mm=230,
                wall_span_m=4.5,
                seismic_zone="I",  # not a valid zone in the table
            )

    def test_invalid_zone_vi_raises_keyerror(self):
        """Zone VI (hypothetical) should raise KeyError."""
        with pytest.raises(KeyError):
            design_seismic_band(
                band_type="lintel",
                wall_thickness_mm=230,
                wall_span_m=4.5,
                seismic_zone="VI",
            )


class TestBandGeometry:
    """Test band geometric output."""

    def test_band_width_equals_wall_thickness(self):
        """Band width should equal wall thickness."""
        wall_thick = 230.0
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=wall_thick,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert result.ok
        assert result.data["width_mm"] == wall_thick

    def test_band_type_output(self):
        """Band type should be preserved in output."""
        result_lintel = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert result_lintel.data["band_type"] == "lintel"

        result_roof = design_seismic_band(
            band_type="roof",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert result_roof.data["band_type"] == "roof"


class TestChecks:
    """Test check list and ok flag."""

    def test_all_checks_pass_nominal_case(self):
        """Nominal case should pass all checks."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="III",
        )
        assert result.ok
        assert len(result.checks) > 0
        # All checks should pass
        for check_name, check_result in result.checks:
            assert check_result, f"Check failed: {check_name}"

    def test_result_is_bandresult(self):
        """design_seismic_band should return a BandResult instance."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="II",
        )
        assert isinstance(result, BandResult)
        assert isinstance(result.ok, bool)
        assert isinstance(result.checks, list)
        assert isinstance(result.data, dict)


class TestZoneCase:
    """Test zone string case-insensitivity."""

    def test_lowercase_zone_ii(self):
        """Lowercase zone 'ii' should work (uppercase internally)."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="ii",
        )
        assert result.ok
        assert result.data["seismic_zone"] == "II"

    def test_mixed_case_zone_iii(self):
        """Mixed case 'iIi' should work (uppercase internally)."""
        result = design_seismic_band(
            band_type="lintel",
            wall_thickness_mm=230,
            wall_span_m=4.5,
            seismic_zone="iIi",
        )
        assert result.ok
        assert result.data["seismic_zone"] == "III"
