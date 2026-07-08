from pathlib import Path
import uuid

import pytest
import requests

BASE_URL = "http://127.0.0.1:5000"
ROOT_DIR = Path(__file__).resolve().parent
MOVIES_CSV = ROOT_DIR / "movies.csv"
CREDITS_CSV = ROOT_DIR / "credits.csv"


def unique_name(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def login(username, password):
    """Helper: login and return bearer token headers."""
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_user(admin_headers, username=None, password="pass123"):
    """Helper: create a normal user through admin endpoint."""
    username = username or unique_name("user")
    resp = requests.post(
        f"{BASE_URL}/auth/users",
        json={"username": username, "password": password},
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"Create user failed: {resp.text}"
    return {
        "id": resp.json()["id"],
        "username": username,
        "password": password,
    }


def create_playlist(headers, name=None):
    """Helper: create a playlist for the current user."""
    name = name or unique_name("playlist")
    resp = requests.post(
        f"{BASE_URL}/playlists",
        json={"name": name},
        headers=headers,
    )
    assert resp.status_code == 201, f"Create playlist failed: {resp.text}"
    return resp.json()


def add_movie_to_playlist(headers, playlist_id, movie_id):
    """Helper: add a movie to a playlist."""
    resp = requests.post(
        f"{BASE_URL}/playlists/{playlist_id}/movies",
        json={"movie_id": movie_id},
        headers=headers,
    )
    return resp


@pytest.fixture(scope="session")
def admin_headers():
    """Session fixture: admin token for protected endpoints."""
    return login("admin", "admin")


@pytest.fixture(scope="session")
def user_headers():
    """Session fixture: default normal user token for protected endpoints."""
    return login("user", "user")


@pytest.fixture(scope="session")
def imported_movies(admin_headers):
    """Session fixture: import movies.csv and credits.csv once for movie tests."""
    with MOVIES_CSV.open("rb") as movies_fp, CREDITS_CSV.open("rb") as credits_fp:
        resp = requests.post(
            f"{BASE_URL}/movies/import",
            headers=admin_headers,
            files={
                "movies_file": ("movies.csv", movies_fp, "text/csv"),
                "credits_file": ("credits.csv", credits_fp, "text/csv"),
            },
        )

    assert resp.status_code == 200, f"Movie import failed: {resp.text}"
    body = resp.json()
    assert body["movies_count"] > 0
    return body


class TestReq1UserManagement:
    """Requirement Set 1: User Management and Access Control."""

    def test_req1_login_success(self):
        """Req 1: Successful login returns 200 with access_token."""
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin"},
        )

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_req1_login_invalid_password(self):
        """Req 1: Invalid password returns 401 with an error message."""
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )

        assert resp.status_code == 401
        assert "invalid" in resp.text.lower()

    def test_req1_login_missing_password(self):
        """Req 1: Missing password returns 400 with validation message."""
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin"},
        )

        assert resp.status_code == 400
        assert "required" in resp.text.lower()

    def test_req1_admin_can_create_user(self, admin_headers):
        """Req 1: Admin can create accounts."""
        username = unique_name("hack")
        resp = requests.post(
            f"{BASE_URL}/auth/users",
            json={"username": username, "password": "hack"},
            headers=admin_headers,
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["username"] == username
        assert body["role"] == "user"
        assert body["is_active"] is True

    def test_req1_user_cannot_create_user(self, user_headers):
        """Req 1: Non-admin user cannot create accounts (403)."""
        resp = requests.post(
            f"{BASE_URL}/auth/users",
            json={"username": unique_name("hack"), "password": "hack"},
            headers=user_headers,
        )

        assert resp.status_code == 403
        assert "access required" in resp.text.lower()

    def test_req1_duplicate_username_returns_409(self, admin_headers):
        """Req 1: Creating an existing username returns 409 conflict."""
        data = create_user(admin_headers, password="dup123")
        resp = requests.post(
            f"{BASE_URL}/auth/users",
            json={"username": data["username"], "password": "dup123"},
            headers=admin_headers,
        )

        assert resp.status_code == 409
        assert "already exists" in resp.text.lower()

    def test_req1_no_token_returns_401(self):
        """Req 1: Accessing protected endpoint without token returns 401."""
        resp = requests.get(f"{BASE_URL}/auth/users")

        assert resp.status_code == 401
        assert "missing" in resp.text.lower() or "authorization" in resp.text.lower()

    def test_req1_admin_can_list_users(self, admin_headers):
        """Req 1: Admin can retrieve paginated user list with full details."""
        resp = requests.get(
            f"{BASE_URL}/auth/users",
            headers=admin_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert {"page", "per_page", "total", "users"}.issubset(body.keys())
        assert isinstance(body["users"], list)
        assert body["per_page"] == 10

    def test_req1_user_cannot_list_all_users(self, user_headers):
        """Req 1: Non-admin user cannot access the all-users management endpoint."""
        resp = requests.get(
            f"{BASE_URL}/auth/users",
            headers=user_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 403
        assert "access required" in resp.text.lower()

    def test_req1_admin_can_get_single_user(self, admin_headers):
        """Req 1: Admin can retrieve one user with paginated single-item query."""
        data = create_user(admin_headers, password="single123")
        resp = requests.get(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == data["id"]
        assert body["username"] == data["username"]
        assert body["role"] == "user"

    def test_req1_patch_requires_is_active_field(self, admin_headers):
        """Req 1: PATCH user without is_active returns 400 with a clear message."""
        data = create_user(admin_headers, password="patchreq123")
        resp = requests.patch(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
            json={},
        )

        assert resp.status_code == 400
        assert "missing is_active" in resp.text.lower()

    def test_req1_admin_can_deactivate_user_and_login_fails(self, admin_headers):
        """Req 1: Deactivated user loses API access and cannot log in."""
        data = create_user(admin_headers, password="deactivate123")
        patch_resp = requests.patch(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
            json={"is_active": False},
        )

        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_active"] is False

        login_resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": data["username"], "password": data["password"]},
        )
        assert login_resp.status_code == 403
        assert "deactivated" in login_resp.text.lower()

    def test_req1_admin_can_reactivate_user(self, admin_headers):
        """Req 1: Admin can reactivate a previously created user."""
        data = create_user(admin_headers, password="reactivate123")
        requests.patch(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
            json={"is_active": False},
        )

        resp = requests.patch(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
            json={"is_active": True},
        )

        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_req1_admin_cannot_delete_admin(self, admin_headers):
        """Req 1: Dedicated admin account cannot be deleted."""
        resp = requests.delete(f"{BASE_URL}/auth/users/1", headers=admin_headers)

        assert resp.status_code == 403
        assert "cannot be deleted" in resp.text.lower()

    def test_req1_admin_can_delete_normal_user(self, admin_headers):
        """Req 1: Admin can delete a normal user account."""
        data = create_user(admin_headers, password="delete123")
        resp = requests.delete(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == data["id"]

    def test_req1_create_user_increases_user_count(self, admin_headers):
        """Req 1: Creating a new user increases the total user count by 1."""
        before_resp = requests.get(
            f"{BASE_URL}/auth/users",
            headers=admin_headers,
            params={"page": 1, "per_page": 100},
        )
        assert before_resp.status_code == 200
        before_total = before_resp.json()["total"]

        username = unique_name("count_user")
        create_resp = requests.post(
            f"{BASE_URL}/auth/users",
            json={"username": username, "password": "count123"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201

        after_resp = requests.get(
            f"{BASE_URL}/auth/users",
            headers=admin_headers,
            params={"page": 1, "per_page": 100},
        )
        assert after_resp.status_code == 200
        after_total = after_resp.json()["total"]

        assert after_total == before_total + 1

    def test_req1_delete_user_decreases_user_count(self, admin_headers):
        """Req 1: Deleting a normal user decreases the total user count by 1."""
        data = create_user(admin_headers, password="drop123")

        before_resp = requests.get(
            f"{BASE_URL}/auth/users",
            headers=admin_headers,
            params={"page": 1, "per_page": 100},
        )
        assert before_resp.status_code == 200
        before_total = before_resp.json()["total"]

        delete_resp = requests.delete(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
        )
        assert delete_resp.status_code == 200

        after_resp = requests.get(
            f"{BASE_URL}/auth/users",
            headers=admin_headers,
            params={"page": 1, "per_page": 100},
        )
        assert after_resp.status_code == 200
        after_total = after_resp.json()["total"]

        assert after_total == before_total - 1


class TestReq2Movies:
    """Requirement Set 2: Movie import and exploration."""

    def test_req2_admin_can_import_movies(self, admin_headers, imported_movies):
        """Req 2: Admin can import movie and credits CSV files."""
        assert imported_movies["movies_count"] > 0
        assert imported_movies["cast_count"] > 0
        assert imported_movies["crew_count"] > 0

    def test_req2_user_cannot_import_movies(self, user_headers):
        """Req 2: Non-admin user cannot import movie CSV files."""
        with MOVIES_CSV.open("rb") as movies_fp, CREDITS_CSV.open("rb") as credits_fp:
            resp = requests.post(
                f"{BASE_URL}/movies/import",
                headers=user_headers,
                files={
                    "movies_file": ("movies.csv", movies_fp, "text/csv"),
                    "credits_file": ("credits.csv", credits_fp, "text/csv"),
                },
            )

        assert resp.status_code == 403
        assert "access required" in resp.text.lower()

    def test_req2_movies_title_search_returns_results(self, imported_movies):
        """Req 2: GET /movies supports fuzzy title search with pagination."""
        resp = requests.get(
            f"{BASE_URL}/movies",
            params={"title": "Avatar", "page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert {"page", "per_page", "total", "movies"}.issubset(body.keys())
        assert body["total"] >= 1
        assert isinstance(body["movies"], list)
        assert len(body["movies"]) >= 1

    def test_req2_movies_combined_search_intersection(self, imported_movies):
        """Req 2: Combined fuzzy filters return intersection-style movie matches."""
        resp = requests.get(
            f"{BASE_URL}/movies",
            params={
                "title": "Avatar",
                "cast": "Sam Worthington",
                "page": 1,
                "per_page": 10,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert any(movie["title"] == "Avatar" for movie in body["movies"])

    def test_req2_movies_cast_lookup_uses_pagination(self, imported_movies):
        """Req 2: GET /movies/cast/{person_id} returns paginated movies for one cast member."""
        resp = requests.get(
            f"{BASE_URL}/movies/cast/65731",
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert {"page", "per_page", "total", "movies"}.issubset(body.keys())
        assert any(movie["title"] == "Avatar" for movie in body["movies"])

    def test_req2_movies_crew_lookup_uses_pagination(self, imported_movies):
        """Req 2: GET /movies/crew/{person_id} returns paginated movies for one crew member."""
        resp = requests.get(
            f"{BASE_URL}/movies/crew/1721",
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert {"page", "per_page", "total", "movies"}.issubset(body.keys())
        assert body["total"] >= 1
        assert isinstance(body["movies"], list)

    def test_req2_movies_playlist_lookup_empty_when_playlist_has_no_movies(
        self, user_headers, imported_movies
    ):
        """Req 2: GET /movies/playlist/{playlist_id} returns empty paginated result for empty playlist."""
        playlist = create_playlist(user_headers)
        resp = requests.get(
            f"{BASE_URL}/movies/playlist/{playlist['id']}",
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["movies"] == []


class TestReq3Playlists:
    """Requirement Set 3: Private playlist management."""

    def test_req3_user_can_create_playlist(self, user_headers):
        """Req 3: Logged-in user can create a private playlist."""
        name = unique_name("playlist")
        resp = requests.post(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            json={"name": name},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == name
        assert "id" in body

    def test_req3_no_token_cannot_create_playlist(self):
        """Req 3: Creating a playlist without token returns 401."""
        resp = requests.post(
            f"{BASE_URL}/playlists",
            json={"name": unique_name("playlist")},
        )

        assert resp.status_code == 401

    def test_req3_duplicate_playlist_name_returns_409(self, user_headers):
        """Req 3: Duplicate playlist name for the same user returns 409."""
        name = unique_name("playlist_dup")
        first = requests.post(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            json={"name": name},
        )
        second = requests.post(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            json={"name": name},
        )

        assert first.status_code == 201
        assert second.status_code == 409
        assert "already exists" in second.text.lower()

    def test_req3_list_playlists_is_paginated(self, user_headers):
        """Req 3: GET /playlists returns paginated playlists for the current user."""
        create_playlist(user_headers)
        resp = requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert {"page", "per_page", "total", "playlists"}.issubset(body.keys())
        assert isinstance(body["playlists"], list)

    def test_req3_create_playlist_increases_count(self, user_headers):
        """Req 3: Creating a playlist increases the current user's playlist count by 1."""
        before_resp = requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 100},
        )
        assert before_resp.status_code == 200
        before_total = before_resp.json()["total"]

        create_resp = requests.post(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            json={"name": unique_name("playlist_count")},
        )
        assert create_resp.status_code == 201

        after_resp = requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 100},
        )
        assert after_resp.status_code == 200
        after_total = after_resp.json()["total"]

        assert after_total == before_total + 1

    def test_req3_get_playlist_detail_uses_pagination(self, user_headers):
        """Req 3: GET /playlists/{id} follows the project's paginated GET style."""
        playlist = create_playlist(user_headers)
        resp = requests.get(
            f"{BASE_URL}/playlists/{playlist['id']}",
            headers=user_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert any(p["id"] == playlist["id"] for p in body["playlists"])

    def test_req3_other_user_cannot_access_playlist(self, admin_headers):
        """Req 3: Non-owner normal users cannot access someone else's playlist."""
        user_a = create_user(admin_headers, password="owner123")
        user_b = create_user(admin_headers, password="viewer123")
        owner_headers = login(user_a["username"], user_a["password"])
        outsider_headers = login(user_b["username"], user_b["password"])
        playlist = create_playlist(owner_headers)

        resp = requests.get(
            f"{BASE_URL}/playlists/{playlist['id']}",
            headers=outsider_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 403
        assert "not the playlist owner" in resp.text.lower()

    def test_req3_can_add_movie_to_playlist(self, user_headers, imported_movies):
        """Req 3: Playlist owner can add a movie to a playlist."""
        playlist = create_playlist(user_headers)
        resp = add_movie_to_playlist(user_headers, playlist["id"], 19995)

        assert resp.status_code == 200
        assert resp.json()["id"] == playlist["id"]

    def test_req3_cannot_add_same_movie_twice(self, user_headers, imported_movies):
        """Req 3: Adding the same movie twice returns 400."""
        playlist = create_playlist(user_headers)
        first = add_movie_to_playlist(user_headers, playlist["id"], 19995)
        second = add_movie_to_playlist(user_headers, playlist["id"], 19995)

        assert first.status_code == 200
        assert second.status_code == 400
        assert "already exists" in second.text.lower()

    def test_req3_can_remove_movie_from_playlist(self, user_headers, imported_movies):
        """Req 3: Playlist owner can remove a movie from a playlist."""
        playlist = create_playlist(user_headers)
        add_movie_to_playlist(user_headers, playlist["id"], 19995)
        resp = requests.delete(
            f"{BASE_URL}/playlists/{playlist['id']}/movies/19995",
            headers=user_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == playlist["id"]

    def test_req3_delete_playlist_success(self, user_headers):
        """Req 3: Playlist owner can delete a playlist."""
        playlist = create_playlist(user_headers)
        resp = requests.delete(
            f"{BASE_URL}/playlists/{playlist['id']}",
            headers=user_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == playlist["id"]

    def test_req3_delete_playlist_decreases_count(self, user_headers):
        """Req 3: Deleting a playlist decreases the current user's playlist count by 1."""
        playlist = create_playlist(user_headers)

        before_resp = requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 100},
        )
        assert before_resp.status_code == 200
        before_total = before_resp.json()["total"]

        delete_resp = requests.delete(
            f"{BASE_URL}/playlists/{playlist['id']}",
            headers=user_headers,
        )
        assert delete_resp.status_code == 200

        after_resp = requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 100},
        )
        assert after_resp.status_code == 200
        after_total = after_resp.json()["total"]

        assert after_total == before_total - 1


class TestReq4Stats:
    """Requirement Set 4: Usage statistics exports."""

    def test_req4_user_can_download_own_usage_csv(self, user_headers):
        """Req 4: Regular users can download CSV stats for their own activity."""
        requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 10},
        )
        resp = requests.get(f"{BASE_URL}/stats/usage/csv", headers=user_headers)

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "timestamp,user_id,username,endpoint,method,status_code" in resp.text

    def test_req4_admin_can_filter_usage_csv_by_user_id(self, admin_headers):
        """Req 4: Admin can filter usage CSV export by user_id query parameter."""
        resp = requests.get(
            f"{BASE_URL}/stats/usage/csv",
            headers=admin_headers,
            params={"user_id": 2},
        )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "timestamp,user_id,username,endpoint,method,status_code" in resp.text
        assert "attachment; filename=usage_stats.csv" in resp.headers.get(
            "content-disposition", ""
        )

    def test_req4_user_can_download_usage_chart(self, user_headers):
        """Req 4: Regular users can download PNG chart for their own activity."""
        requests.get(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            params={"page": 1, "per_page": 10},
        )
        resp = requests.get(f"{BASE_URL}/stats/usage/chart", headers=user_headers)

        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")
        assert len(resp.content) > 0

    def test_req4_admin_can_download_usage_chart(self, admin_headers):
        """Req 4: Admin can also download PNG chart output."""
        resp = requests.get(
            f"{BASE_URL}/stats/usage/chart",
            headers=admin_headers,
        )

        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")
        assert len(resp.content) > 0

    def test_req4_no_token_on_stats_returns_401(self):
        """Req 4: Accessing stats endpoints without token returns 401."""
        resp = requests.get(f"{BASE_URL}/stats/usage/csv")

        assert resp.status_code == 401


class TestEdgeCases:
    """Edge case coverage required by Requirement Set 6."""

    def test_edge_auth_patch_missing_field_returns_400(self, admin_headers):
        """Edge: PATCH /auth/users/{id} without is_active returns 400."""
        data = create_user(admin_headers, password="patch123")
        resp = requests.patch(
            f"{BASE_URL}/auth/users/{data['id']}",
            headers=admin_headers,
            json={},
        )

        assert resp.status_code == 400
        assert "missing is_active" in resp.text.lower()

    def test_edge_auth_get_missing_user_returns_404(self, admin_headers):
        """Edge: GET /auth/users/{id} returns 404 for a missing user."""
        resp = requests.get(
            f"{BASE_URL}/auth/users/999999",
            headers=admin_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_edge_playlist_missing_name_returns_400(self, user_headers):
        """Edge: Creating a playlist without name returns 400."""
        resp = requests.post(
            f"{BASE_URL}/playlists",
            headers=user_headers,
            json={},
        )

        assert resp.status_code == 400
        assert "required" in resp.text.lower()

    def test_edge_add_missing_movie_id_returns_400(self, user_headers):
        """Edge: Adding movie to playlist without movie_id returns 400."""
        playlist = create_playlist(user_headers)
        resp = requests.post(
            f"{BASE_URL}/playlists/{playlist['id']}/movies",
            headers=user_headers,
            json={},
        )

        assert resp.status_code == 400
        assert "movie_id is required" in resp.text.lower()

    def test_edge_playlist_add_nonexistent_movie_returns_404(self, user_headers):
        """Edge: Adding a nonexistent movie to playlist returns 404."""
        playlist = create_playlist(user_headers)
        resp = requests.post(
            f"{BASE_URL}/playlists/{playlist['id']}/movies",
            headers=user_headers,
            json={"movie_id": 99999999},
        )

        assert resp.status_code == 404
        assert "movie not found" in resp.text.lower()

    def test_edge_playlist_missing_playlist_returns_404(self, user_headers):
        """Edge: Accessing a missing playlist returns 404."""
        resp = requests.get(
            f"{BASE_URL}/playlists/99999999",
            headers=user_headers,
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 404
        assert "playlist not found" in resp.text.lower()

    def test_edge_remove_nonexistent_movie_from_playlist_returns_404(
        self, user_headers
    ):
        """Edge: Removing a movie not in playlist returns 404."""
        playlist = create_playlist(user_headers)
        resp = requests.delete(
            f"{BASE_URL}/playlists/{playlist['id']}/movies/999999",
            headers=user_headers,
        )

        assert resp.status_code == 404
        assert "movie not found" in resp.text.lower() or "not in playlist" in resp.text.lower()

    def test_edge_movies_invalid_import_without_files_returns_400(self, admin_headers):
        """Edge: Import endpoint returns 400 when CSV files are missing."""
        resp = requests.post(
            f"{BASE_URL}/movies/import",
            headers=admin_headers,
        )

        assert resp.status_code in {400, 415}

    def test_edge_movies_unknown_cast_returns_empty_paginated_result(
        self, imported_movies
    ):
        """Edge: Unknown cast person returns an empty paginated movies list."""
        resp = requests.get(
            f"{BASE_URL}/movies/cast/99999999",
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["movies"] == []

    def test_edge_movies_unknown_crew_returns_empty_paginated_result(
        self, imported_movies
    ):
        """Edge: Unknown crew person returns an empty paginated movies list."""
        resp = requests.get(
            f"{BASE_URL}/movies/crew/99999999",
            params={"page": 1, "per_page": 10},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["movies"] == []