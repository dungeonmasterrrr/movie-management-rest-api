import csv
import io
import json
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from flask import Flask, Response, request, send_file
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)
from flask_restx import Api, Namespace, Resource, fields
from flask_sqlalchemy import SQLAlchemy
from rapidfuzz import fuzz, process
from rapidfuzz import utils as rfuzz_utils
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash, generate_password_hash


# config.py

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///asmt2.db"

# optional
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# User login uses JWT

# JWT storage
app.config["JWT_SECRET_KEY"] = "super-secret-key-for-assignment"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
app.config["RESTX_MASK_SWAGGER"] = False

# Initialize the database
db = SQLAlchemy(app)
# Initialize JWT
jwt = JWTManager(app)

authorizations = {
    "Bearer": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": "Enter: Bearer <your_token>",
    }
}

api = Api(
    app,
    version="1.0",
    title="Assignment 2 API",
    description="RESTful API for movie data with Admin/User roles",
    authorizations=authorizations,
    security="Bearer",
)

# set timezone
SYDNEY_TZ = ZoneInfo("Australia/Sydney")


# models.py


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(length=80), unique=True, nullable=False)
    password_hash = db.Column(db.String(length=256), nullable=False)
    role = db.Column(db.String(length=20), default="user", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(SYDNEY_TZ),
        nullable=False,
    )

    playlists = db.relationship(
        "Playlist",
        backref="owner",
        cascade="all, delete-orphan",
    )
    api_usages = db.relationship(
        "ApiUsage",
        backref="user",
        cascade="all, delete-orphan",
    )


class Movie(db.Model):
    __tablename__ = "movie"

    # Movie ids come from the imported CSV rather than auto-increment.
    # A few varchar lengths below are chosen as practical storage limits only.
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(length=300))
    budget = db.Column(db.Float)
    genres = db.Column(db.Text)
    homepage = db.Column(db.Text)
    original_language = db.Column(db.String(length=20))
    original_title = db.Column(db.String(length=500))
    overview = db.Column(db.Text)
    popularity = db.Column(db.Float)
    production_companies = db.Column(db.Text)
    production_countries = db.Column(db.Text)
    release_date = db.Column(db.String(length=50))
    revenue = db.Column(db.Float)
    runtime = db.Column(db.Float)
    spoken_languages = db.Column(db.Text)
    status = db.Column(db.String(length=50))
    tagline = db.Column(db.Text)
    vote_average = db.Column(db.Float)
    vote_count = db.Column(db.Integer)
    keywords = db.Column(db.Text)

    # One movie can have multiple cast members and crew members.
    cast_members = db.relationship("CastMember", backref="movie")
    crew_members = db.relationship("CrewMember", backref="movie")


class CastMember(db.Model):
    __tablename__ = "cast_member"

    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(
        db.Integer,
        db.ForeignKey("movie.id"),
        nullable=False,
        index=True,
    )
    person_id = db.Column(db.Integer, index=True)
    cast_id = db.Column(db.Integer)
    name = db.Column(db.String(length=255))
    character = db.Column(db.String(length=300))
    gender = db.Column(db.Integer)
    cast_order = db.Column("order", db.Integer)
    profile_path = db.Column(db.String(length=300))


class CrewMember(db.Model):
    __tablename__ = "crew_member"

    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(
        db.Integer,
        db.ForeignKey("movie.id"),
        nullable=False,
        index=True,
    )
    person_id = db.Column(db.Integer, index=True)
    name = db.Column(db.String(length=300))
    department = db.Column(db.String(length=200))
    job = db.Column(db.String(length=200))
    gender = db.Column(db.Integer)
    profile_path = db.Column(db.String(length=300))


class Playlist(db.Model):
    __tablename__ = "playlist"
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_playlist_user_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(length=120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(SYDNEY_TZ),
        nullable=False,
    )

    # Playlist and Movie are linked via the playlist_movies association table.
    movies = db.relationship(
        "Movie",
        secondary="playlist_movies",
        backref="playlists",
    )


class PlaylistMovie(db.Model):
    __tablename__ = "playlist_movies"

    playlist_id = db.Column(
        db.Integer,
        db.ForeignKey("playlist.id"),
        primary_key=True,
    )
    movie_id = db.Column(
        db.Integer,
        db.ForeignKey("movie.id"),
        primary_key=True,
    )


class ApiUsage(db.Model):
    __tablename__ = "api_usage"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    endpoint = db.Column(db.String(length=500))
    method = db.Column(db.String(length=10))
    status_code = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime)


# helpers.py

# Parse JSON fields
def parse_json_field(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


# Get the current user from the JWT
def get_current_user():
    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id))
    if user and user.is_active:
        return user
    return None


# Check whether the current user has a specific role
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


# Build the API usage query
def build_usage_query(user, is_admin):
    stmt = db.select(ApiUsage)
    if is_admin:
        # Admin can use ?user_id=123 to view a specific user
        target_user_id = request.args.get("user_id", type=int)
        if target_user_id:
            stmt = stmt.filter_by(user_id=target_user_id)
        else:
            # By default, view all non-admin data
            stmt = stmt.filter(ApiUsage.user_id != user.id)
    else:
        stmt = stmt.filter_by(user_id=user.id)
    return stmt


# middleware.py

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


# auth.py

auth_ns = Namespace("auth", description="Authentication and user management")

credentials_model = auth_ns.model(
    "Credentials",
    {
        "username": fields.String(required=True, description="Username"),
        "password": fields.String(required=True, description="Password"),
    },
)

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

    # All GET requests should use pagination
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
        # Check whether the user to delete is an admin; if so, do not delete
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
        # All GET requests should use pagination
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

# movies.py

movies_ns = Namespace("movies", description="Movie data import and exploration")

# Main challenge
# It used to be JSON; now we need to handle CSV. How should we do it?
import_parser = movies_ns.parser()
import_parser.add_argument(
    "movies_file",
    location="files",
    type=FileStorage,
    required=True,
    help="movies.csv file",
)
import_parser.add_argument(
    "credits_file",
    location="files",
    type=FileStorage,
    required=True,
    help="credits.csv file",
)

movie_response = movies_ns.model(
    "MovieResponse",
    {
        "id": fields.Integer,
        "title": fields.String,
        "budget": fields.Float,
        "genres": fields.String,
        "homepage": fields.String,
        "original_language": fields.String,
        "original_title": fields.String,
        "overview": fields.String,
        "popularity": fields.Float,
        "production_companies": fields.String,
        "production_countries": fields.String,
        "release_date": fields.String,
        "revenue": fields.Float,
        "runtime": fields.Float,
        "spoken_languages": fields.String,
        "status": fields.String,
        "tagline": fields.String,
        "vote_average": fields.Float,
        "vote_count": fields.Integer,
        "keywords": fields.String,
    },
)

movie_list_response = movies_ns.model(
    "MovieListResponse",
    {
        "page": fields.Integer,
        "per_page": fields.Integer,
        "total": fields.Integer,
        "movies": fields.List(fields.Nested(movie_response)),
    },
)


@movies_ns.route("/import")
class MovieImportResource(Resource):
    @movies_ns.doc(
        summary="Import movie and credits data",
        description="Admin only. Upload movies.csv and credits.csv to replace existing movie data.",
    )
    @movies_ns.expect(import_parser)
    @movies_ns.response(200, "Import successful")
    @movies_ns.response(400, "Invalid CSV file")
    @movies_ns.response(401, "Missing or invalid token")
    @movies_ns.response(403, "Admin access required")
    @role_required("admin")
    def post(self):
        args = import_parser.parse_args()
        movies_file = args.movies_file
        credits_file = args.credits_file

        # Read files with pandas
        try:
            movies_df = pd.read_csv(movies_file)
        except Exception as e:
            api.abort(400, f"Error reading movies file: {e}")
            return

        try:
            credits_df = pd.read_csv(credits_file)
        except Exception as e:
            api.abort(400, f"Error reading credits file: {e}")
            return

        # How should NaN and empty values be handled?
        movies_df = movies_df.where(movies_df.notna(), None)
        credits_df = credits_df.where(credits_df.notna(), None)

        # Why do this
        # Because pandas automatically converts empty CSV values to NaN
        # The database would otherwise store this as the string "nan"

        # Handle missing values

        # Remove duplicates
        movies_df = movies_df.drop_duplicates(subset=["id"], keep="first")
        credits_df = credits_df.drop_duplicates(subset=["movie_id"], keep="first")

        # Clear old data
        # Reimport means replacing data instead of appending new data
        db.session.execute(db.delete(PlaylistMovie))
        db.session.execute(db.delete(CastMember))
        db.session.execute(db.delete(CrewMember))
        db.session.execute(db.delete(Movie))

        movies_count = 0
        cast_count = 0
        crew_count = 0

        for _, row in movies_df.iterrows():
            movie_id = row.get("id")
            if movie_id is None:
                continue

            movie = Movie(
                id=int(movie_id),
                title=row.get("title"),
                budget=row.get("budget"),
                genres=row.get("genres"),
                homepage=row.get("homepage"),
                original_language=row.get("original_language"),
                original_title=row.get("original_title"),
                overview=row.get("overview"),
                popularity=row.get("popularity"),
                production_companies=row.get("production_companies"),
                production_countries=row.get("production_countries"),
                release_date=row.get("release_date"),
                revenue=row.get("revenue"),
                runtime=row.get("runtime"),
                spoken_languages=row.get("spoken_languages"),
                status=row.get("status"),
                tagline=row.get("tagline"),
                vote_average=row.get("vote_average"),
                vote_count=row.get("vote_count"),
                keywords=row.get("keywords"),
            )

            db.session.add(movie)
            movies_count += 1

        for _, row in credits_df.iterrows():
            movie_id = row.get("movie_id")
            if movie_id is None:
                continue

            cast_items = parse_json_field(row.get("cast"))
            for item in cast_items:
                cast_member = CastMember(
                    movie_id=int(movie_id),
                    person_id=item.get("id"),
                    cast_id=item.get("cast_id"),
                    name=item.get("name"),
                    character=item.get("character"),
                    gender=item.get("gender"),
                    cast_order=item.get("order"),
                    profile_path=item.get("profile_path"),
                )
                db.session.add(cast_member)
                cast_count += 1

            crew_items = parse_json_field(row.get("crew"))
            for item in crew_items:
                crew_member = CrewMember(
                    movie_id=int(movie_id),
                    person_id=item.get("id"),
                    name=item.get("name"),
                    department=item.get("department"),
                    job=item.get("job"),
                    gender=item.get("gender"),
                    profile_path=item.get("profile_path"),
                )
                db.session.add(crew_member)
                crew_count += 1

        db.session.commit()

        return {
            "message": "Import successful",
            "movies_count": movies_count,
            "cast_count": cast_count,
            "crew_count": crew_count,
        }


# First define a helper function
def fuzzy_match(query_str, choices):
    if not choices:
        return set()
    matches = process.extract(
        query_str,
        [name for name, _ in choices],
        scorer=fuzz.WRatio,  # Similarity algorithm
        processor=rfuzz_utils.default_process,  # Convert to lowercase automatically
        score_cutoff=60,  # Scores above 60 count as a match
        limit=None,
    )
    return {choices[r[2]][1] for r in matches}


@movies_ns.route("")
class MovieListResource(Resource):
    @movies_ns.doc(
        summary="List movies",
        description="Returns paginated movies filtered by fuzzy title, cast, or crew search.",
    )
    @movies_ns.param("title", "Fuzzy search by movie title")
    @movies_ns.param("cast", "Fuzzy search by cast member name")
    @movies_ns.param("crew", "Fuzzy search by crew member name")
    @movies_ns.param("page", "Page number (default: 1)", type=int)
    @movies_ns.param("per_page", "Items per page (default: 10)", type=int)
    @movies_ns.marshal_with(movie_list_response)
    @movies_ns.response(200, "Success", movie_list_response)
    @movies_ns.response(400, "Invalid query parameters")
    def get(self):
        title_q = request.args.get("title")
        cast_q = request.args.get("cast")
        crew_q = request.args.get("crew")
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        # If search parameters are provided, use fuzzy matching
        result_sets = []
        if title_q:
            titles = [
                (m.title, m.id)
                for m in db.session.scalars(db.select(Movie))
                if m.title
            ]
            result_sets.append(fuzzy_match(title_q, titles))
        if cast_q:
            cast_names = [
                (c.name, c.movie_id)
                for c in db.session.scalars(db.select(CastMember))
                if c.name
            ]
            result_sets.append(fuzzy_match(cast_q, cast_names))
        if crew_q:
            crew_names = [
                (c.name, c.movie_id)
                for c in db.session.scalars(db.select(CrewMember))
                if c.name
            ]
            result_sets.append(fuzzy_match(crew_q, crew_names))

        # What if both title and cast are searched at the same time?
        # Use the intersection of common query conditions
        # title="pirates" cast="Johnny Depp"
        # Only return movies whose title contains pirates and whose cast includes Johnny Depp
        final_ids = result_sets[0] if result_sets else set()
        for s in result_sets[1:]:
            final_ids = final_ids & s

        # All GET requests should use pagination
        # Fuzzy search results are computed in Python memory rather than fetched from the database
        # So manual slicing is needed
        sorted_ids = sorted(final_ids)
        total = len(sorted_ids)
        start = (page - 1) * per_page
        page_ids = sorted_ids[start : start + per_page]

        movies = (
            db.session.scalars(
                db.select(Movie).filter(Movie.id.in_(page_ids)).order_by(Movie.id)
            ).all()
            if page_ids
            else []
        )

        return {"page": page, "per_page": per_page, "total": total, "movies": movies}


# Please use pagination for the results!!!
@movies_ns.route("/cast/<int:person_id>")
class CastResource(Resource):
    @movies_ns.doc(
        summary="List movies by cast member",
        description="Returns paginated movies for a given cast person id.",
    )
    @movies_ns.param("page", "Page number (default: 1)", type=int)
    @movies_ns.param("per_page", "Items per page (default: 10)", type=int)
    @movies_ns.marshal_with(movie_list_response)
    @movies_ns.response(200, "Success", movie_list_response)
    @movies_ns.response(404, "Cast person not found or has no movies")
    def get(self, person_id):
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        stmt = (
            db.select(Movie)
            .join(CastMember, CastMember.movie_id == Movie.id)
            .filter(CastMember.person_id == person_id)
            .order_by(Movie.id)
        )
        pagination = db.paginate(
            stmt,
            page=page,
            per_page=per_page,
            error_out=False,
        )

        return {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "movies": pagination.items,
        }


@movies_ns.route("/crew/<int:person_id>")
class CrewResource(Resource):
    @movies_ns.doc(
        summary="List movies by crew member",
        description="Returns paginated movies for a given crew person id.",
    )
    @movies_ns.param("page", "Page number (default: 1)", type=int)
    @movies_ns.param("per_page", "Items per page (default: 10)", type=int)
    @movies_ns.marshal_with(movie_list_response)
    @movies_ns.response(200, "Success", movie_list_response)
    @movies_ns.response(404, "Crew person not found or has no movies")
    def get(self, person_id):
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        stmt = (
            db.select(Movie)
            .join(CrewMember, CrewMember.movie_id == Movie.id)
            .filter(CrewMember.person_id == person_id)
            .order_by(Movie.id)
        )
        pagination = db.paginate(
            stmt,
            page=page,
            per_page=per_page,
            error_out=False,
        )

        return {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "movies": pagination.items,
        }


@movies_ns.route("/playlist/<int:playlist_id>")
class PlaylistResource(Resource):
    @movies_ns.doc(
        summary="List movies in a playlist",
        description="Returns paginated movies for a given playlist id.",
    )
    @movies_ns.param("page", "Page number (default: 1)", type=int)
    @movies_ns.param("per_page", "Items per page (default: 10)", type=int)
    @movies_ns.marshal_with(movie_list_response)
    @movies_ns.response(200, "Success", movie_list_response)
    @movies_ns.response(404, "Playlist not found or has no movies")
    def get(self, playlist_id):
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        stmt = (
            db.select(Movie)
            .join(PlaylistMovie, PlaylistMovie.movie_id == Movie.id)
            .filter(PlaylistMovie.playlist_id == playlist_id)
            .order_by(Movie.id)
        )
        pagination = db.paginate(
            stmt,
            page=page,
            per_page=per_page,
            error_out=False,
        )

        return {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "movies": pagination.items,
        }


# playlists.py

playlists_ns = Namespace("playlists", description="Private playlist management")

playlist_response = playlists_ns.model(
    "PlaylistResponse",
    {
        "id": fields.Integer,
        "name": fields.String,
        "user_id": fields.Integer,
        "created_at": fields.DateTime(dt_format="iso8601"),
    },
)

playlist_list_response = playlists_ns.model(
    "PlaylistListResponse",
    {
        "page": fields.Integer,
        "per_page": fields.Integer,
        "total": fields.Integer,
        "playlists": fields.List(fields.Nested(playlist_response)),
    },
)

playlist_create_model = playlists_ns.model(
    "PlaylistCreate",
    {
        "name": fields.String(required=True, description="Playlist name"),
    },
)

playlist_movie_model = playlists_ns.model(
    "PlaylistMovieAdd",
    {
        "movie_id": fields.Integer(required=True, description="Movie id to add"),
    },
)

playlist_movie_response = playlists_ns.model(
    "PlaylistMovieResponse",
    {
        "id": fields.Integer,
        "title": fields.String,
        "budget": fields.Float,
        "genres": fields.String,
        "homepage": fields.String,
        "original_language": fields.String,
        "original_title": fields.String,
        "overview": fields.String,
        "popularity": fields.Float,
        "production_companies": fields.String,
        "production_countries": fields.String,
        "release_date": fields.String,
        "revenue": fields.Float,
        "runtime": fields.Float,
        "spoken_languages": fields.String,
        "status": fields.String,
        "tagline": fields.String,
        "vote_average": fields.Float,
        "vote_count": fields.Integer,
        "keywords": fields.String,
    },
)

playlist_movie_list_response = playlists_ns.model(
    "PlaylistMovieListResponse",
    {
        "page": fields.Integer,
        "per_page": fields.Integer,
        "total": fields.Integer,
        "movies": fields.List(fields.Nested(playlist_movie_response)),
    },
)


def check_owner(playlist):
    if playlist.user_id != int(get_jwt_identity()) and get_jwt().get("role") != "admin":
        api.abort(403, "Access denied - not the playlist owner")


@playlists_ns.route("")
class PlaylistListResource(Resource):
    @playlists_ns.doc(
        summary="List playlists",
        description="Returns paginated playlists for the current user. Admin can see all playlists.",
    )
    @playlists_ns.param("page", "Page number (default: 1)", type=int)
    @playlists_ns.param("per_page", "Items per page (default: 10)", type=int)
    @playlists_ns.marshal_with(playlist_list_response)
    @playlists_ns.response(200, "Success", playlist_list_response)
    @playlists_ns.response(401, "Missing or invalid token")
    @role_required()
    def get(self):
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        stmt = db.select(Playlist)
        if get_jwt().get("role") != "admin":
            stmt = stmt.filter_by(user_id=int(get_jwt_identity()))

        pagination = db.paginate(
            stmt.order_by(Playlist.id),
            page=page,
            per_page=per_page,
            error_out=False,
        )

        return {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "playlists": pagination.items,
        }

    @playlists_ns.doc(
        summary="Create a playlist",
        description="Create a new private playlist for the current user.",
    )
    @playlists_ns.expect(playlist_create_model)
    @playlists_ns.marshal_with(playlist_response, code=201)
    @playlists_ns.response(400, "Missing playlist name")
    @playlists_ns.response(409, "Playlist name already exists")
    @playlists_ns.response(401, "Missing or invalid token")
    @role_required()
    def post(self):
        # Validate the data first
        # Return an error if name is empty
        # Playlist names must be unique
        # Return an error if the name already exists
        # The rest is the same; refer to the auth and movies patterns
        data = request.json or {}
        name = data.get("name")
        if not name:
            api.abort(400, "Playlist name is required")
            return

        user_id = int(get_jwt_identity())
        if db.session.scalar(db.select(Playlist).filter_by(user_id=user_id, name=name)):
            api.abort(409, "Playlist name already exists")
            return

        playlist = Playlist(name=name, user_id=user_id)
        db.session.add(playlist)
        db.session.commit()
        return playlist, 201


@playlists_ns.route("/<int:playlist_id>")
class PlaylistDetailResource(Resource):
    @playlists_ns.doc(
        summary="Get a playlist",
        description="Returns one playlist after owner/admin permission check.",
    )
    @playlists_ns.param("page", "Page number (default: 1)", type=int)
    @playlists_ns.param("per_page", "Items per page (default: 10)", type=int)
    @playlists_ns.marshal_with(playlist_list_response)
    @playlists_ns.response(404, "Playlist not found")
    @playlists_ns.response(403, "Access denied - not the playlist owner")
    @playlists_ns.response(401, "Missing or invalid token")
    @role_required()
    def get(self, playlist_id):
        # Need to check the owner
        playlist = db.session.get(Playlist, playlist_id)
        if not playlist:
            api.abort(404, "Playlist not found")
            return
        check_owner(playlist)

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        pagination = db.paginate(
            db.select(Playlist).filter_by(id=playlist_id),
            page=page,
            per_page=per_page,
            error_out=False,
        )

        return {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "playlists": pagination.items,
        }

    @playlists_ns.doc(
        summary="Delete a playlist",
        description="Delete a playlist after owner/admin permission check.",
    )
    @playlists_ns.marshal_with(playlist_response)
    @playlists_ns.response(404, "Playlist not found")
    @playlists_ns.response(403, "Access denied - not the playlist owner")
    @playlists_ns.response(401, "Missing or invalid token")
    @role_required()
    def delete(self, playlist_id):
        # Need to check the owner
        playlist = db.session.get(Playlist, playlist_id)
        if not playlist:
            api.abort(404, "Playlist not found")
            return
        check_owner(playlist)

        db.session.delete(playlist)
        db.session.commit()
        return playlist, 200


@playlists_ns.route("/<int:playlist_id>/movies")
class PlaylistMovieAddResource(Resource):
    @playlists_ns.doc(
        summary="Add a movie to a playlist",
        description="Add one movie to a playlist after owner/admin permission check.",
    )
    @playlists_ns.expect(playlist_movie_model)
    @playlists_ns.marshal_with(playlist_response)
    @playlists_ns.response(400, "Movie already exists in playlist or missing movie_id")
    @playlists_ns.response(404, "Playlist or movie not found")
    @playlists_ns.response(403, "Access denied - not the playlist owner")
    @playlists_ns.response(401, "Missing or invalid token")
    @role_required()
    def post(self, playlist_id):
        # Need to check the owner
        playlist = db.session.get(Playlist, playlist_id)
        if not playlist:
            api.abort(404, "Playlist not found")
            return
        check_owner(playlist)

        data = request.json or {}
        movie_id = data.get("movie_id")
        if movie_id is None:
            api.abort(400, "movie_id is required")
            return

        movie = db.session.get(Movie, int(movie_id))
        if not movie:
            api.abort(404, "Movie not found")
            return
        if any(m.id == movie.id for m in playlist.movies):
            api.abort(400, "Movie already exists in playlist")
            return

        playlist.movies.append(movie)
        db.session.commit()
        return playlist, 200


@playlists_ns.route("/<int:playlist_id>/movies/<int:movie_id>")
class PlaylistMovieRemoveResource(Resource):
    @playlists_ns.doc(
        summary="Remove a movie from a playlist",
        description="Remove one movie from a playlist after owner/admin permission check.",
    )
    @playlists_ns.marshal_with(playlist_response)
    @playlists_ns.response(404, "Playlist or movie not found")
    @playlists_ns.response(403, "Access denied - not the playlist owner")
    @playlists_ns.response(401, "Missing or invalid token")
    @role_required()
    def delete(self, playlist_id, movie_id):
        # Need to check the owner
        playlist = db.session.get(Playlist, playlist_id)
        if not playlist:
            api.abort(404, "Playlist not found")
            return
        check_owner(playlist)

        movie = db.session.get(Movie, movie_id)
        if not movie:
            api.abort(404, "Movie not found")
            return
        if all(m.id != movie.id for m in playlist.movies):
            api.abort(404, "Movie is not in playlist")
            return

        playlist.movies.remove(movie)
        db.session.commit()
        return playlist, 200


# stats.py

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

        # Preload all related usernames at once
        # Querying the database inside the loop would mean hundreds of queries for hundreds of records
        # Query once, store the results in a dictionary, and read from it inside the loop
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

        # TODO: pandas pivot table:
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

        # TODO: draw with matplotlib (make sure the Agg backend is set at the top of the file first):
        fig, ax = plt.subplots(figsize=(10, 6))
        pivot.plot(kind="bar", ax=ax)
        ax.set_title("API Usage - Daily Requests per Endpoint")
        ax.set_xlabel("Date")
        ax.set_ylabel("Request Count")

        # TODO: compare the output with the CSV version:
        # CSV: output = io.StringIO() -> Response(mimetype="text/csv")
        # Image: buf = io.BytesIO() -> send_file(buf, mimetype="image/png")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)  # Be sure to close after plotting, or there will be a memory leak
        buf.seek(0)
        return send_file(buf, mimetype="image/png")


# seed.py

def seed_default_accounts():
    if not db.session.scalar(db.select(User).filter_by(username="admin")):
        db.session.add(
            User(
                username="admin",
                password_hash=generate_password_hash("admin"),
                role="admin",
            )
        )

    if not db.session.scalar(db.select(User).filter_by(username="user")):
        db.session.add(
            User(
                username="user",
                password_hash=generate_password_hash("user"),
                role="user",
            )
        )

    db.session.commit()


# app.py

api.add_namespace(auth_ns)
api.add_namespace(movies_ns)
api.add_namespace(playlists_ns)
api.add_namespace(stats_ns)

with app.app_context():
    db.create_all()
    seed_default_accounts()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
