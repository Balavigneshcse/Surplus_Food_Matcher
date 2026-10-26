"""Route log (revision 0006): where leftovers went. The waste hierarchy is enforced by CHECKs."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RouteLog(Base):
    __tablename__ = "route_log"
    __table_args__ = (
        CheckConstraint("category in ('RESERVE_DONATED', 'RESERVE_UNCLAIMED', 'RESERVE_UNSAFE', 'COOKED_UNSERVED',"
                        " 'PLATE_WASTE', 'RAW_VEG_TRIMMINGS')", name="ck_route_log_category"),
        CheckConstraint("destination in ('NGO', 'CATTLE_FEED', 'BIOGAS', 'COMPOST', 'LANDFILL')",
                        name="ck_route_log_destination"),
        CheckConstraint("qty_g > 0", name="ck_route_log_qty"),
        # cooked food never goes to cattle feed
        CheckConstraint("destination <> 'CATTLE_FEED' or category = 'RAW_VEG_TRIMMINGS'",
                        name="ck_cattle_raw_veg_only"),
        # only the donated reserve goes to an NGO, and it always goes to an NGO
        CheckConstraint("(destination = 'NGO') = (category = 'RESERVE_DONATED')", name="ck_ngo_only_donated"),
        CheckConstraint("category not like 'RESERVE%' or batch_id is not null", name="ck_reserve_has_batch"),
        # landfill is the logged last resort
        CheckConstraint("destination <> 'LANDFILL' or reason is not null", name="ck_landfill_reason"),
        Index("ix_route_log_kitchen_logged_at", "kitchen_id", "logged_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kitchen_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("kitchen.id"))
    meal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("meal.id"))
    batch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("reserve_batch.id"))
    category: Mapped[str] = mapped_column(String(20))
    destination: Mapped[str] = mapped_column(String(12))
    qty_g: Mapped[int]
    reason: Mapped[str | None] = mapped_column(String(200))
    logged_at: Mapped[datetime]
    logged_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
