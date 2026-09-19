"""Funnel reporting: conversion, decline reasons, withdrawals, sources."""

from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required

from ..constants import Stage
from ..reporting import (
    children_in_window,
    conversion_summary,
    funnel_rows,
    monthly_inquiries,
    reason_breakdown,
    source_breakdown,
    stage_counts,
)
from ..utils import parse_date

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@login_required
def index():
    # Default window: the last 12 months of inquiries.
    today = date.today()
    start = parse_date(request.args.get("start")) or (today - timedelta(days=365))
    end = parse_date(request.args.get("end")) or today

    children = children_in_window(start=start, end=end)

    return render_template(
        "reports/index.html",
        start=start,
        end=end,
        children=children,
        summary=conversion_summary(children),
        funnel=funnel_rows(children),
        stage_counts=stage_counts(children),
        decline_reasons=reason_breakdown(children, Stage.DECLINED),
        withdraw_reasons=reason_breakdown(children, Stage.WITHDREW),
        sources=source_breakdown(children),
        monthly=monthly_inquiries(today=today),
    )
