# Movie RESTful API

## Project Overview

This project is a Flask-based RESTful API for movie data management.

The API supports user authentication, role-based access control, movie data import, fuzzy movie search, private playlist management, and API usage statistics. It uses JWT tokens for authentication and SQLite with SQLAlchemy for local data storage.

This project demonstrates backend development skills including REST API design, database modelling, authentication, authorization, pagination, CSV import, data export, and automated API testing.

## Key Features

- User login with JWT authentication
- Admin and regular user role management
- Admin-only user creation, deletion, activation, and deactivation
- Movie and credits CSV import
- Movie search by title, cast, and crew using fuzzy matching
- Paginated movie results
- Private playlist creation and management
- Add and remove movies from playlists
- Owner-based playlist access control
- API usage logging for authenticated requests
- Export API usage statistics as CSV
- Export API usage statistics as PNG chart
- Automated API testing with pytest

## Technologies Used

- Python
- Flask
- Flask-RESTX
- Flask-SQLAlchemy
- Flask-JWT-Extended
- SQLite
- pandas
- RapidFuzz
- Matplotlib
- pytest
- requests

## Project Structure

```text
movie-restful-api/
│
├── api.py
├── app.py
├── tests.py
├── requirements.txt
├── description.ipynb
├── movies.csv
├── credits.csv
├── README.md
│
└── src/
    ├── auth.py
    ├── config.py
    ├── helpers.py
    ├── middleware.py
    ├── models.py
    ├── movies.py
    ├── playlists.py
    ├── seed.py
    └── stats.py
```

## Files Not Included in Public Repository

The following files and folders are intentionally excluded from the public repository:

```text
key.txt
__pycache__/
instance/asmt2.db
```

Reasons:

- `key.txt` may contain local secrets or configuration values.
- `__pycache__/` contains Python cache files and is not needed.
- `instance/asmt2.db` is a local SQLite database generated during development.

A new local database can be created automatically when the application runs.

## File Description

### `api.py`

Contains the main API implementation, including Flask app setup, database models, authentication routes, movie routes, playlist routes, statistics routes, and API usage logging.

### `app.py`

Application entry point for running the Flask server.

### `tests.py`

Contains automated tests for authentication, user management, movie import, movie search, playlist management, API usage statistics, and edge cases.

### `requirements.txt`

Lists the required Python packages for this project.

### `description.ipynb`

Contains project notes or development description in Jupyter Notebook format.

### `movies.csv`

Movie metadata dataset used for importing movie records into the database.

### `credits.csv`

Credits dataset containing cast and crew information.

### `src/`

Contains modular source files for different parts of the backend system:

- `auth.py`: authentication and user management
- `config.py`: Flask, database, and JWT configuration
- `helpers.py`: helper functions and role-checking logic
- `middleware.py`: API usage logging middleware
- `models.py`: SQLAlchemy database models
- `movies.py`: movie import, search, cast, and crew routes
- `playlists.py`: playlist creation and management routes
- `seed.py`: default account seeding
- `stats.py`: API usage statistics export routes

## Main API Modules

## 1. Authentication and User Management

The API supports JWT-based login.

Default accounts are created when the application starts:

```text
admin / admin
user / user
```

Admin users can:

- Create new users
- List all users
- View user details
- Activate or deactivate users
- Delete normal users

Regular users cannot access admin-only user management endpoints.

## 2. Movie Import and Search

Admin users can import movie data from:

```text
movies.csv
credits.csv
```

The API stores movie metadata, cast members, and crew members in the database.

Movie search supports:

- Fuzzy title search
- Fuzzy cast search
- Fuzzy crew search
- Combined search filters
- Pagination

Example search:

```http
GET /movies?title=Avatar&page=1&per_page=10
```

Combined search example:

```http
GET /movies?title=Avatar&cast=Sam Worthington&page=1&per_page=10
```

## 3. Playlist Management

Authenticated users can create and manage private playlists.

Users can:

- Create playlists
- View their own playlists
- Add movies to playlists
- Remove movies from playlists
- Delete playlists

Access control ensures that normal users cannot access playlists owned by other users.

## 4. API Usage Statistics

The API logs authenticated requests and stores usage records.

Users can download their own API usage statistics.

Admins can view broader usage statistics and filter by user ID.

Supported export formats:

```text
CSV
PNG chart
```

The CSV export includes:

```text
timestamp
user_id
username
endpoint
method
status_code
```

The PNG chart visualises daily API requests by endpoint.

## How to Run

### 1. Clone this repository

```bash
git clone https://github.com/your-username/movie-restful-api.git
```

### 2. Open the project folder

```bash
cd movie-restful-api
```

### 3. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Activate it on macOS or Linux:

```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the Flask application

```bash
python app.py
```

Or, if using `api.py` as the main file:

```bash
python api.py
```

The API will run locally at:

```text
http://127.0.0.1:5000
```

## API Documentation

This project uses Flask-RESTX, so interactive API documentation is available after running the app.

Open this URL in the browser:

```text
http://127.0.0.1:5000/
```

You can test routes directly from the Swagger interface.

## Example API Usage

### Login

```http
POST /auth/login
```

Request body:

```json
{
  "username": "admin",
  "password": "admin"
}
```

Response:

```json
{
  "access_token": "your_jwt_token"
}
```

Use the token in the request header:

```text
Authorization: Bearer your_jwt_token
```

## Import Movies

```http
POST /movies/import
```

Admin only.

Upload:

```text
movies_file = movies.csv
credits_file = credits.csv
```

## Search Movies

```http
GET /movies?title=Avatar&page=1&per_page=10
```

## Create Playlist

```http
POST /playlists
```

Request body:

```json
{
  "name": "My Favourite Movies"
}
```

## Add Movie to Playlist

```http
POST /playlists/{playlist_id}/movies
```

Request body:

```json
{
  "movie_id": 19995
}
```

## Download Usage Statistics

CSV export:

```http
GET /stats/usage/csv
```

PNG chart export:

```http
GET /stats/usage/chart
```

## Running Tests

Make sure the Flask app is running first:

```bash
python app.py
```

Then open another terminal and run:

```bash
pytest tests.py
```

The tests cover:

- Login and authentication
- Admin user management
- Movie import
- Movie search
- Playlist creation and deletion
- Movie addition and removal from playlists
- API usage CSV export
- API usage chart export
- Error handling and edge cases

## Notes

This project was created for learning and portfolio purposes. It demonstrates backend API development using Flask, SQLAlchemy, JWT authentication, role-based access control, fuzzy search, API usage monitoring, and automated testing.

If this project was developed from coursework, the repository should remain private unless public sharing is allowed.
