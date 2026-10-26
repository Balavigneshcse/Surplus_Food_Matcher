"""Errors as RFC 9457 problem details (application/problem+json) with an extra `code` field."""
import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


class ApiError(Exception):
    """Raise this from services/routers to answer with a problem+json error."""

    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


# Database constraint name -> (code, message). Unknown names fall back to CONSTRAINT_VIOLATED.
CONSTRAINT_CODES: dict[str, tuple[str, str]] = {
    "ck_cattle_raw_veg_only": ("CATTLE_FEED_RAW_VEG_ONLY", "Only raw vegetable trimmings may go to cattle feed"),
    "ck_ngo_only_donated": ("NGO_ONLY_FOR_DONATED_RESERVE", "Only a donated reserve batch goes to an NGO"),
    "ck_reserve_has_batch": ("RESERVE_NEEDS_BATCH", "A reserve category needs a batch"),
    "ck_landfill_reason": ("LANDFILL_NEEDS_REASON", "Landfill is the last resort and needs a reason"),
    "ux_offer_one_taker": ("OFFER_NOT_OPEN", "This batch already has a taker"),
    "ux_offer_one_pending": ("OFFER_ALREADY_PENDING", "This batch already has an open offer"),
    "uq_offer_batch_ngo": ("ALREADY_OFFERED", "This NGO was already offered this batch"),
    "uq_offer_batch_seq": ("OFFER_SEQ_TAKEN", "This offer step was already used"),
    "ux_meal_one_reserve": ("ONE_RESERVE_DISH", "A meal has exactly one reserve dish"),
    "uq_meal_kitchen_slot_date": ("MEAL_EXISTS", "This meal already exists"),
    "uq_meal_dish_meal_dish": ("DISH_ALREADY_ON_MENU", "This dish is already on the menu"),
    "uq_reserve_batch_meal": ("RESERVE_ALREADY_LIDDED", "This meal already has a reserve vessel"),
    "uq_opt_out_kitchen_slot_date_hostel": ("ALREADY_OPTED_OUT", "You have already opted out of this meal"),
    "uq_app_user_username": ("USERNAME_TAKEN", "This username is taken"),
    "uq_kitchen_code": ("KITCHEN_CODE_TAKEN", "This kitchen code is taken"),
    "uq_partnership_kitchen_ngo": ("PARTNERSHIP_EXISTS", "This kitchen and NGO already have an MoU"),
    "uq_dish_kitchen_name": ("DISH_NAME_TAKEN", "A dish with this name already exists"),
    "uq_meal_slot_kitchen_slot": ("SLOT_EXISTS", "This meal slot already exists"),
    "uq_batch_record_batch": ("RECORD_EXISTS", "This batch already has a record"),
    "uq_reserve_batch_batch_no": ("BATCH_NO_TAKEN", "This batch number is already used"),
    "ck_probe_temp_range": ("TEMP_OUT_OF_RANGE", "The temperature must be between -10 and 120 °C"),
    "ck_meal_p90_ge_p50": ("P90_BELOW_P50", "The high forecast (P90) must not be below the expected one (P50)"),
    "ck_meal_manual_reason": ("OVERRIDE_NEEDS_REASON", "A manual forecast needs a reason"),
    "ck_meal_closed_has_actual": ("ACTUAL_DINERS_REQUIRED", "Closing a meal needs the actual number of diners"),
    "ck_batch_record_distribution_once": ("DISTRIBUTION_INCOMPLETE",
                                          "Quantity, area and date of distribution are entered together"),
}
# tests/integration/test_migrations.py checks that every name above really exists in the database.


def constraint_code(exc: IntegrityError) -> tuple[str, str]:
    """Map an IntegrityError to (code, message) using the database constraint name."""
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None) or ""
    return CONSTRAINT_CODES.get(name, ("CONSTRAINT_VIOLATED", "The change breaks a data rule"))


def problem(request: Request, status: int, code: str, detail: str,
            headers: dict | None = None, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status,
            "detail": detail, "instance": request.url.path, "code": code, **extra}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def _safe_errors(exc: RequestValidationError) -> list:
    # Never echo the submitted values back: they may contain a password.
    cleaned = [{k: v for k, v in err.items() if k not in ("input", "url")} for err in exc.errors()]
    return jsonable_encoder(cleaned)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError):
        return problem(request, exc.status, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)  # FastAPI's default is 422; we use 400
    async def on_invalid(request: Request, exc: RequestValidationError):
        return problem(request, 400, "VALIDATION_FAILED", "Some fields are invalid",
                       errors=_safe_errors(exc))

    @app.exception_handler(StarletteHTTPException)  # unknown paths (404), 405, ...
    async def on_http(request: Request, exc: StarletteHTTPException):
        return problem(request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail),
                       headers=getattr(exc, "headers", None))

    @app.exception_handler(IntegrityError)
    async def on_integrity(request: Request, exc: IntegrityError):
        code, detail = constraint_code(exc)
        return problem(request, 409, code, detail)

    @app.exception_handler(StaleDataError)  # the optimistic lock (version column) lost a race
    async def on_stale(request: Request, exc: StaleDataError):
        return problem(request, 409, "CONCURRENT_EDIT",
                       "Someone else changed this just now. Reload and try again.")

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, exc: Exception):
        log.exception("unexpected error on %s", request.url.path)
        return problem(request, 500, "INTERNAL_ERROR", "Something went wrong on the server")
