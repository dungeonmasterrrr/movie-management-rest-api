from flask import request
from flask_jwt_extended import create_access_token
from flask_restx import Namespace, Resource, fields
from werkzeug.security import check_password_hash, generate_password_hash

from src.config import api, db
from src.helpers import role_required
from src.models import User

auth_ns = Namespace("auth", description="Authentication and user management")

# model (request)
credentials_model = auth_ns.model(
    "Credentials",
    {
        "username": fields.String(required=True, description="Username"),
        "password": fields.String(required=True, description="Password"),
    },
)

# response
login_response = auth_ns.model(
    "LoginResponse",
    {
        "access_token": fields.String(description="JWT access token"),
    },
)

user_response = auth_ns.model(
    "UserResponse",
    {
        "id": fields.Integer,
        "username": fields.String,
        "role": fields.String,
        "is_active": fields.Boolean,
        "created_at": fields.DateTime(dt_format="iso8601"),
    },
)

user_list_response = auth_ns.model(
    "UserListResponse",
    {
        "page": fields.Integer,
        "per_page": fields.Integer,
        "total": fields.Integer,
        "users": fields.List(fields.Nested(user_response)),
    },
)

patch_user_model = auth_ns.model(
    "PatchUser",
    {
        "is_active": fields.Boolean(required=True, description="Active status"),
    },
)


# login in
@auth_ns.route("/login")
class LoginResource(Resource):
    @auth_ns.doc(
        summary="Login",
        description="Authenticate with username and password to receive a JWT access token",
    )
    @auth_ns.expect(credentials_model)
    @auth_ns.marshal_with(login_response)
    @auth_ns.response(200, "Login successful", login_response)
    @auth_ns.response(400, "Missing username or password")
    @auth_ns.response(401, "Invalid credentials")
    @auth_ns.response(403, "Account is deactivated")
    def post(self):
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            api.abort(400, "Username and password are required")
            return

        user = db.session.scalar(db.select(User).filter_by(username=username))
        if not user or not check_password_hash(user.password_hash, password):
            api.abort(401, "Invalid username or password")
            return

        if not user.is_active:
            api.abort(403, "Account is deactivated")

        token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role},
        )

        return {"access_token": token}, 200


@auth_ns.route("/users")
class UserListResource(Resource):
    @auth_ns.doc(
        summary="List all users",
        description="Admin only. Returns paginated list of all user accounts.",
    )
    @auth_ns.param("page", "Page number (default: 1)", type=int)
    @auth_ns.param("per_page", "Items per page (default: 10)", type=int)
    @auth_ns.marshal_with(user_list_response)
    @auth_ns.response(401, "Missing or invalid token")
    @auth_ns.response(403, "Admin access required")
    @role_required("admin")
    def get(self):
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        pagination = db.paginate(
            db.select(User), page=page, per_page=per_page, error_out=False
        )

        return {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "users": pagination.items,
        }

    # 所有的 get 都要用 pagination
    @auth_ns.doc(
        summary="Create a new user",
        description="Admin only. Role is always 'user' - cannot create admin via API.",
    )
    @auth_ns.expect(credentials_model)
    @auth_ns.marshal_with(user_response, code=201)
    @auth_ns.response(400, "Missing username or password")
    @auth_ns.response(409, "Username already exists")
    @role_required("admin")
    def post(self):
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            api.abort(400, "Username and password are required")
            return

        if db.session.scalar(db.select(User).filter_by(username=username)):
            api.abort(409, "Username already exists")
            return

        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role="user",
        )

        db.session.add(new_user)
        db.session.commit()
        return new_user, 201


@auth_ns.route("/users/<int:user_id>")
class UserResource(Resource):
    @auth_ns.marshal_with(user_response)
    @auth_ns.response(403, "Admin user cannot be deleted")
    @auth_ns.response(404, "User not found")
    @role_required("admin")
    def delete(self, user_id):
        # 检查想要删除的用户是否是 admin，如果是，则不能删除
        # db.session.delete(user) + db.session.commit()
        user = db.session.get(User, user_id)
        if not user:
            api.abort(404, "User not found")
            return
        if user.role == "admin":
            api.abort(403, "Admin user cannot be deleted")
            return

        db.session.delete(user)
        db.session.commit()
        return user, 200

    @auth_ns.marshal_with(user_response)
    @auth_ns.response(404, "User not found")
    @auth_ns.param("page", "Page number (default: 1)", type=int)
    @auth_ns.param("per_page", "Items per page (default: 10)", type=int)
    @role_required("admin")
    def get(self, user_id):
        # 所有的 get 都要用 pagination
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        pagination = db.paginate(
            db.select(User).filter_by(id=user_id),
            page=page,
            per_page=per_page,
            error_out=False,
        )
        if not pagination.items:
            api.abort(404, "User not found")
            return
        return pagination.items[0], 200

    @auth_ns.expect(patch_user_model)
    @auth_ns.marshal_with(user_response)
    @auth_ns.response(400, "Missing is_active field")
    @auth_ns.response(404, "User not found")
    @role_required("admin")
    def patch(self, user_id):
        data = request.json or {}
        user = db.session.get(User, user_id)
        if not user:
            api.abort(404, "User not found")
            return
        if "is_active" not in data:
            api.abort(400, "Missing is_active field")
            return

        # user.is_active = data["is_active"]
        # db.session.commit()
        user.is_active = data["is_active"]
        db.session.commit()
        return user, 200
