import csv
import io
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pandas as pd
from flask import Response, send_file
from flask_jwt_extended import get_jwt
from flask_restx import Namespace, Resource

from src.config import db
from src.helpers import build_usage_query, get_current_user, role_required
from src.models import ApiUsage, User

stats_ns = Namespace("stats", description="Api usage statistics")

@stats_ns.route("/usage/csv")
class StatsCSVResource(Resource):
    @stats_ns.doc(
        summary="Download usage CSV",
        description="Download API usage statistics as a CSV file. Admin can view all users' stats (excluding own activity by default) or filter by user_id. Regular users see only their own stats.",
    )
    @stats_ns.param("user_id", "Filter by user ID (admin only)", type=int)
    @stats_ns.response(200, "Success")
    @stats_ns.response(401, "Missing or invalid token")
    @stats_ns.response(403, "Account is deactivated or not found")
    @role_required()
    def get(self):
        user = get_current_user()

        is_admin = get_jwt().get("role") == "admin"
        stmt = build_usage_query(user, is_admin)
        records = db.session.scalars(
            stmt.order_by(ApiUsage.timestamp.desc())
        ).all()

        # 预先一次性查好所有相关用户的用户名
        # 如果在循环里每次都去查数据库，几百条记录就要查几百次，非常慢
        # 先查一次存在字典里，循环里直接用字典取就行
        user_ids = {r.user_id for r in records}
        user_map = {
            u.id: u.username
            for u in db.session.scalars(
                db.select(User).filter(User.id.in_(user_ids))
            )
        }

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["timestamp", "user_id", "username", "endpoint", "method", "status_code"]
        )
        for r in records:
            writer.writerow(
                [
                    r.timestamp.isoformat() if r.timestamp else "",
                    r.user_id,
                    user_map.get(r.user_id, "unknown"),
                    r.endpoint,
                    r.method,
                    r.status_code,
                ]
            )

        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=usage_stats.csv"},
        )


@stats_ns.route("/usage/chart")
class StatsPlotResource(Resource):
    @stats_ns.doc(
        summary="Download usage chart",
        description="Download API usage statistics as a PNG chart. Admin can view all users' stats (excluding own activity by default) or filter by user_id. Regular users see only their own stats.",
    )
    @stats_ns.param("user_id", "Filter by user ID (admin only)", type=int)
    @stats_ns.response(200, "Success")
    @stats_ns.response(401, "Missing or invalid token")
    @stats_ns.response(403, "Account is deactivated or not found")
    @role_required()
    def get(self):
        user = get_current_user()

        is_admin = get_jwt().get("role") == "admin"
        stmt = build_usage_query(user, is_admin)
        records = db.session.scalars(
            stmt.order_by(ApiUsage.timestamp.desc())
        ).all()

        data = [
            {
                "date": r.timestamp.date().isoformat() if r.timestamp else "unknown",
                "endpoint": r.endpoint or "unknown",
            }
            for r in records
        ]

        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame([{"date": "no_data", "endpoint": "no_data"}])

        pivot = df.groupby(["date", "endpoint"]).size().unstack(fill_value=0)

        fig, ax = plt.subplots(figsize=(10, 6))
        pivot.plot(kind="bar", ax=ax)
        ax.set_title("API Usage - Daily Requests per Endpoint")
        ax.set_xlabel("Date")
        ax.set_ylabel("Request Count")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)

        return send_file(buf, mimetype="image/png")