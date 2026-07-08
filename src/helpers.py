import json
from functools import wraps

from flask import request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from src.config import api, db
from src.models import ApiUsage, User

# 解析json字段
def parse_json_field(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

# 从当前jwt获取用户
def get_current_user():
    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id))
    if user and user.is_active:
        return user
    return None

# 检查用户是否具有特定的角色
def role_required(role=None):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                api.abort(403, "Account is deactivated or not found")
            if role and get_jwt().get("role") != role:
                api.abort(403, f"{role.title()} access required")
            return fn(*args, **kwargs)

        return wrapper

    return decorator

# 构建api使用的查询语句
def build_usage_query(user, is_admin):
    stmt = db.select(ApiUsage)
    if is_admin:
        target_user_id = request.args.get("user_id", type=int)
        if target_user_id:
            stmt = stmt.filter_by(user_id=target_user_id)
        else:
            stmt = stmt.filter(ApiUsage.user_id != user.id)
    else:
        stmt = stmt.filter_by(user_id=user.id)
    return stmt
    
