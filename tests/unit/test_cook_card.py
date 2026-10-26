"""Cook card and reserve vessel (plan 8.2): integer grams; the pages show kg with one decimal."""
import pytest

from app.rules.cook_card import (P50_TOPUP, P90, CookLine, DishInput, basis_used, cook_card, cook_line,
                                 menu_problem)

RICE = DishInput(cooked_g_per_diner=200, raw_g_per_diner=82, is_reserve=True)
SAMBHAR = DishInput(cooked_g_per_diner=150, raw_g_per_diner=None, is_reserve=False)
PORIYAL = DishInput(cooked_g_per_diner=80, raw_g_per_diner=None, is_reserve=False)
DAL = DishInput(cooked_g_per_diner=120, raw_g_per_diner=40, is_reserve=False)


def kg(g: int) -> str:
    """The same rounding as fmtKg() in static/js/ui.js: from integer grams, half up, one decimal."""
    return f"{(g + 50) // 100 / 10:.1f}"


def test_plan_example_rice_and_sambhar():
    rice, sambhar = cook_card(812, 861, [RICE, SAMBHAR], P50_TOPUP)
    # "Rice: cook 70.6 kg raw -> serving line 162.4 kg cooked + RESERVE VESSEL 9.8 kg cooked"
    assert rice == CookLine(line_g=162400, reserve_g=9800, top_up_g=0, raw_g=70602, raw_diners=861)
    assert (kg(rice.raw_g), kg(rice.line_g), kg(rice.reserve_g)) == ("70.6", "162.4", "9.8")
    # "Sambhar: 121.8 kg + top-up ready for 7.4 kg"
    assert sambhar == CookLine(line_g=121800, reserve_g=0, top_up_g=7350, raw_g=None, raw_diners=812)
    assert (kg(sambhar.line_g), kg(sambhar.top_up_g)) == ("121.8", "7.4")


def test_demo_start_numbers_813_862():
    rice, sambhar, poriyal = cook_card(813, 862, [RICE, SAMBHAR, PORIYAL], P50_TOPUP)
    # demo script 0:00: rice 70.7 kg raw -> serving line 162.6 kg + reserve vessel 9.8 kg
    assert (kg(rice.raw_g), kg(rice.line_g), kg(rice.reserve_g)) == ("70.7", "162.6", "9.8")
    assert (sambhar.line_g, sambhar.top_up_g) == (121950, 7350)
    assert (poriyal.line_g, poriyal.top_up_g) == (65040, 3920)


def test_reserve_dish_raw_amount_covers_p90():
    line = cook_line(812, 861, RICE, P50_TOPUP)
    assert line.raw_diners == 861 and line.raw_g == 861 * 82


def test_reserve_dish_is_the_same_under_both_bases():
    assert cook_line(812, 861, RICE, P50_TOPUP) == cook_line(812, 861, RICE, P90)


def test_side_dish_p50_topup_basis():
    line = cook_line(812, 861, DAL, P50_TOPUP)
    assert line == CookLine(line_g=812 * 120, reserve_g=0, top_up_g=49 * 120, raw_g=812 * 40, raw_diners=812)


def test_side_dish_p90_basis_has_no_top_up():
    line = cook_line(812, 861, DAL, P90)
    assert line == CookLine(line_g=861 * 120, reserve_g=0, top_up_g=0, raw_g=861 * 40, raw_diners=861)


def test_no_raw_amount_when_raw_g_per_diner_is_not_set():
    for basis in (P50_TOPUP, P90):
        assert cook_line(812, 861, SAMBHAR, basis).raw_g is None
    no_raw_reserve = DishInput(cooked_g_per_diner=200, raw_g_per_diner=None, is_reserve=True)
    assert cook_line(812, 861, no_raw_reserve, P50_TOPUP).raw_g is None


def test_equal_p50_and_p90_gives_an_empty_reserve_and_no_top_up():
    rice, sambhar = cook_card(500, 500, [RICE, SAMBHAR], P50_TOPUP)
    assert (rice.reserve_g, sambhar.top_up_g) == (0, 0)


def test_menu_needs_exactly_one_reserve_dish_and_it_must_be_veg():
    assert menu_problem([RICE, SAMBHAR]) is None
    assert menu_problem([SAMBHAR, PORIYAL]) == "ONE_RESERVE_DISH"
    assert menu_problem([RICE, DishInput(150, None, is_reserve=True)]) == "ONE_RESERVE_DISH"
    assert menu_problem([]) == "ONE_RESERVE_DISH"
    chicken = DishInput(cooked_g_per_diner=120, raw_g_per_diner=None, is_reserve=True, is_veg=False)
    assert menu_problem([chicken, SAMBHAR]) == "RESERVE_MUST_BE_VEG"
    with pytest.raises(ValueError, match="ONE_RESERVE_DISH"):
        cook_card(812, 861, [SAMBHAR], P50_TOPUP)
    with pytest.raises(ValueError, match="RESERVE_MUST_BE_VEG"):
        cook_card(812, 861, [chicken], P50_TOPUP)


def test_bad_numbers_are_refused():
    with pytest.raises(ValueError):
        cook_line(861, 812, RICE, P50_TOPUP)  # P90 below P50
    with pytest.raises(ValueError):
        cook_line(-1, 812, RICE, P50_TOPUP)
    with pytest.raises(ValueError):
        cook_line(812, 861, RICE, "P75")


def test_basis_used_reads_the_frozen_card_back():
    p50, p90 = 812, 861
    topup_card = [(p50 * 150, 150), (p50 * 80, 80)]
    p90_card = [(p90 * 150, 150), (p90 * 80, 80)]
    assert basis_used(p50, p90, topup_card) == P50_TOPUP
    assert basis_used(p50, p90, p90_card) == P90
    assert basis_used(p50, p90, []) == P50_TOPUP  # no side dishes: nothing to tell apart
    assert basis_used(500, 500, [(500 * 150, 150)]) == P50_TOPUP  # P50 = P90: both bases give the same card
