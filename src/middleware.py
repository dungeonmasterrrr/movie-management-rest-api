from datetime import datetime

from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from src.config import SYDNEY_TZ, app, db
from src.models import ApiUsage


@app.after_request
def log_api_usage(response):
    """Log every authenticated request for monitoring."""
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            usage = ApiUsage(
                user_id=int(user_id),
                endpoint=request.path,
                method=request.method,
                status_code=response.status_code,
                timestamp=datetime.now(SYDNEY_TZ),
            )
            db.session.add(usage)
            db.session.commit()
    except Exception:
        pass
    return response
