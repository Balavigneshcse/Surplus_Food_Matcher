"""Schemas for organisations and users. (Kitchen/NGO/MoU/user admin schemas arrive with the admin phase.)"""
from app.schemas.common import ApiModel, IstDateTime


class LoginOut(ApiModel):
    role: str
    display_name: str
    csrf_token: str  # login issues a new token; api.js also re-reads it from the cookie


class MeOut(ApiModel):
    id: int
    username: str
    display_name: str
    role: str
    kitchen_id: int | None
    kitchen_code: str | None
    kitchen_name: str | None
    ngo_id: int | None
    ngo_name: str | None
    sample_data: bool  # true in demo mode: pages show the SAMPLE DATA banner
    server_now: IstDateTime  # countdowns use this, never the phone clock
