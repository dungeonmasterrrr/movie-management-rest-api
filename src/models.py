from datetime import datetime

from src.config import SYDNEY_TZ, db


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
