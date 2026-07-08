from src.auth import auth_ns
from src.config import api, app, db
from src.seed import seed_default_accounts
from src import middleware
from src.movies import movies_ns
from src.playlists import playlists_ns
from src.stats import stats_ns

api.add_namespace(auth_ns)
api.add_namespace(movies_ns)
api.add_namespace(playlists_ns)
api.add_namespace(stats_ns)

with app.app_context():
    db.create_all()
    seed_default_accounts()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
