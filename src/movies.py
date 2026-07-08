import json

import pandas as pd
from flask import request
from flask_restx import Namespace, Resource, fields
from rapidfuzz import fuzz, process
from rapidfuzz import utils as rfuzz_utils
from werkzeug.datastructures import FileStorage

from src.config import api, db
from src.helpers import parse_json_field, role_required
from src.models import CastMember, CrewMember, Movie, Playlist, PlaylistMovie

movies_ns = Namespace("movies", description="Movie data import and exploration")

# 难点
# 之前都是 json，现在要处理 csv，怎么做？
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

        # pandas 读取文件
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

        # 如何处理 nan 和空值？
        movies_df = movies_df.where(movies_df.notna(), None)
        credits_df = credits_df.where(credits_df.notna(), None)

        # 为什么要这么做
        # 是因为 csv 空值，pandas 会自动处理成 NaN
        # 数据库会把这个变成字符串 nan

        # 如果有缺失怎么处理

        # 去重
        movies_df = movies_df.drop_duplicates(subset=["id"], keep="first")
        credits_df = credits_df.drop_duplicates(subset=["movie_id"], keep="first")

        # 清空旧数据
        # reimport -> 替换而不是追加新的数据
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


# 先定义一个辅助函数
def fuzzy_match(query_str, choices):
    if not choices:
        return set()

    matches = process.extract(
        query_str,
        [name for name, _ in choices],
        scorer=fuzz.WRatio,  # 相似度算法
        processor=rfuzz_utils.default_process,  # 自动转小写
        score_cutoff=60,  # 60 分以上算匹配
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

        # 如果有搜索参数，就是用模糊匹配
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

        # 如果说同时搜索了 title 和 cast 怎么办呢？
        # 常见题目的交集
        # title="pirates" cast="Johnny Depp"
        # 只返回标题含 pirates 并且演员含 Johnny Depp 的电影
        final_ids = result_sets[0] if result_sets else set()
        for s in result_sets[1:]:
            final_ids = final_ids & s

        # GET 都应该用 pagination
        # 因为模糊搜索的结果是在 Python 内存里算出来的，而不是从数据库里面获取的
        # 需要手动切片
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


# 结果请用 pagination!!!
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
