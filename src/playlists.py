from flask import request
from flask_jwt_extended import get_jwt, get_jwt_identity
from flask_restx import Namespace, Resource, fields

from src.config import api, db
from src.helpers import role_required
from src.models import Movie, Playlist

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

movie_response = playlists_ns.model(
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
        "movies": fields.List(fields.Nested(movie_response)),
    },
)


def check_owner(playlist):
    if (
        playlist.user_id != int(get_jwt_identity())
        and get_jwt().get("role") != "admin"
    ):
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
        # 先数据验证
        # 如果 name 为空，报错
        # playlist 不可重名
        # 如果 name 已经存在，报错
        # 其他的一样（参考 auth&movies 相关的写法）
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
        # 需要 check owner
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
        # 需要 check owner
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
    # @playlists_ns.doc(
    #     summary="List movies in a playlist",
    #     description="Returns paginated movies in a playlist after owner/admin permission check.",
    # )
    # @playlists_ns.param("page", "Page number (default: 1)", type=int)
    # @playlists_ns.param("per_page", "Items per page (default: 10)", type=int)
    # @playlists_ns.marshal_with(playlist_movie_list_response)
    # @playlists_ns.response(404, "Playlist not found")
    # @playlists_ns.response(403, "Access denied - not the playlist owner")
    # @playlists_ns.response(401, "Missing or invalid token")
    # @role_required()
    # def get(self, playlist_id):
    #     playlist = db.session.get(Playlist, playlist_id)
    #     if not playlist:
    #         api.abort(404, "Playlist not found")
    #         return
    #     check_owner(playlist)
    #
    #     page = request.args.get("page", 1, type=int)
    #     per_page = request.args.get("per_page", 10, type=int)
    #     stmt = (
    #         db.select(Movie)
    #         .join(Playlist.movies)
    #         .filter(Playlist.id == playlist_id)
    #         .order_by(Movie.id)
    #     )
    #     pagination = db.paginate(
    #         stmt,
    #         page=page,
    #         per_page=per_page,
    #         error_out=False,
    #     )
    #
    #     return {
    #         "page": pagination.page,
    #         "per_page": pagination.per_page,
    #         "total": pagination.total,
    #         "movies": pagination.items,
    #     }

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
        # 需要 check owner
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
        # 需要 check owner
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
