"""Cook card and reserve vessel amounts (plan 8.2). Pure Python: no FastAPI, no database.

For each dish on the menu (gC = cooked g per diner, gR = raw g per diner or None):

    reserve dish:            line = P50 x gC;  reserve = (P90 - P50) x gC;  raw diners = P90
    side dish, P50_TOPUP:    line = P50 x gC;  reserve = 0;  raw diners = P50
                             plus "top-up ready (20-min quick cook)": (P90 - P50) x gC
    side dish, P90:          line = P90 x gC;  reserve = 0;  raw diners = P90
    raw = None if gR is None else raw diners x gR

Example (P50 812, P90 861; rice 200 g cooked / 82 g raw; sambhar 150 g):
    Rice: cook 70.6 kg raw -> serving line 162.4 kg cooked + RESERVE VESSEL 9.8 kg cooked
    Sambhar: 121.8 kg + top-up ready for 7.4 kg

One reserve dish = one lidded vessel, and in the MVP the reserve dish must be veg (veg and non-veg are
never mixed). All amounts are integer grams; the pages show kg with one decimal.
"""
from dataclasses import dataclass

P50_TOPUP = "P50_TOPUP"
P90 = "P90"
SIDE_DISH_BASES = (P50_TOPUP, P90)


@dataclass(frozen=True)
class DishInput:
    cooked_g_per_diner: int
    raw_g_per_diner: int | None
    is_reserve: bool
    is_veg: bool = True


@dataclass(frozen=True)
class CookLine:
    line_g: int  # cooked grams for the serving line
    reserve_g: int  # cooked grams for the lidded reserve vessel (reserve dish only, else 0)
    top_up_g: int  # cooked grams of the 20-minute quick-cook top-up (P50_TOPUP side dishes only, else 0)
    raw_g: int | None  # raw (uncooked) grams to cook; None when the dish has no raw g/diner
    raw_diners: int  # how many diners the raw amount is for


def menu_problem(dishes: list[DishInput]) -> str | None:
    """None if the menu is fine, else an error code: exactly one reserve dish, and it must be veg."""
    reserve = [d for d in dishes if d.is_reserve]
    if len(reserve) != 1:
        return "ONE_RESERVE_DISH"
    if not reserve[0].is_veg:
        return "RESERVE_MUST_BE_VEG"
    return None


def cook_line(p50: int, p90: int, dish: DishInput, side_dish_basis: str) -> CookLine:
    if p50 < 0 or p90 < p50:
        raise ValueError("need 0 <= P50 <= P90")
    if side_dish_basis not in SIDE_DISH_BASES:
        raise ValueError(f"unknown side dish basis {side_dish_basis!r}")
    g = dish.cooked_g_per_diner
    if dish.is_reserve:
        line_g, reserve_g, top_up_g, raw_diners = p50 * g, (p90 - p50) * g, 0, p90
    elif side_dish_basis == P50_TOPUP:
        line_g, reserve_g, top_up_g, raw_diners = p50 * g, 0, (p90 - p50) * g, p50
    else:  # P90
        line_g, reserve_g, top_up_g, raw_diners = p90 * g, 0, 0, p90
    raw_g = None if dish.raw_g_per_diner is None else raw_diners * dish.raw_g_per_diner
    return CookLine(line_g=line_g, reserve_g=reserve_g, top_up_g=top_up_g, raw_g=raw_g, raw_diners=raw_diners)


def cook_card(p50: int, p90: int, dishes: list[DishInput], side_dish_basis: str) -> list[CookLine]:
    """One CookLine per dish, in the same order. The menu must have exactly one (veg) reserve dish."""
    problem = menu_problem(dishes)
    if problem is not None:
        raise ValueError(problem)
    return [cook_line(p50, p90, dish, side_dish_basis) for dish in dishes]


def basis_used(p50: int, p90: int, side_dishes: list[tuple[int, int]]) -> str:
    """Which side-dish basis an issued card used, read back from its frozen (line_g, cooked g/diner) pairs.

    The kitchen may change its setting after a card is issued; the frozen card must not change with it.
    A P90 side dish has line_g = P90 x g; a P50_TOPUP one has line_g = P50 x g. (If P50 = P90 both give
    the same card.)"""
    for line_g, g in side_dishes:
        if p90 != p50 and line_g == p90 * g:
            return P90
    return P50_TOPUP
