"""Tests for Pydantic model validation logic in models.py."""

import pytest
from pydantic import ValidationError

from custom_components.ssd_ims.models import ChartData, PointOfDelivery


class TestPointOfDeliveryId:
    def test_extracts_id_from_text_with_trailing_description(self):
        pod = PointOfDelivery(text="99XXX1234560000G (Rodinný dom)", value="v1")
        assert pod.id == "99XXX1234560000G"

    def test_text_that_is_already_a_bare_id_is_returned_as_is(self):
        pod = PointOfDelivery(text="99XXX1234560000G", value="v1")
        assert pod.id == "99XXX1234560000G"

    def test_unparseable_text_fails_construction(self):
        """ID extraction happens once, at construction time — a POD with
        unparseable text fails to construct at all (ValidationError, which
        is also a ValueError) rather than existing as a half-valid object
        whose `.id` can raise wherever it's later accessed."""
        with pytest.raises(ValueError, match="Could not extract valid POD ID"):
            PointOfDelivery(text="not a valid pod identifier", value="v1")

    def test_too_short_id_like_text_fails_construction(self):
        with pytest.raises(ValueError):
            PointOfDelivery(text="TOOSHORT123 (Home)", value="v1")


class TestChartDataFloatListValidation:
    def test_none_entries_are_zero_filled_not_dropped(self):
        chart_data = ChartData(
            meteringDatetime=["2025-01-20T10:15:00Z", "2025-01-20T10:30:00Z"],
            actualConsumption=[1.5, None],
            actualSupply=[None, 2.5],
        )

        assert chart_data.actual_consumption == [1.5, 0.0]
        assert chart_data.actual_supply == [0.0, 2.5]

    def test_single_numeric_value_is_wrapped_in_a_list(self):
        chart_data = ChartData(actualConsumption=3.5)
        assert chart_data.actual_consumption == [3.5]

    def test_unconvertible_single_value_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Expected list or numeric value"):
            ChartData(actualConsumption="not-a-number")

    def test_unconvertible_list_item_raises_validation_error_with_index(self):
        with pytest.raises(ValidationError, match="at index 1"):
            ChartData(actualConsumption=[1.0, "garbage", 2.0])


class TestChartDataSumFieldValidation:
    def test_none_sum_defaults_to_zero(self):
        chart_data = ChartData(sumActualConsumption=None)
        assert chart_data.sum_actual_consumption == 0.0

    def test_numeric_string_sum_is_converted(self):
        chart_data = ChartData(sumActualConsumption="12.5")
        assert chart_data.sum_actual_consumption == 12.5

    def test_unconvertible_sum_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Cannot convert"):
            ChartData(sumActualConsumption="not-a-number")
