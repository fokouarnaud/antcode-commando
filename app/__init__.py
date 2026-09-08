import flask

from app.database import get_connection


def create_app(db_path, webhook_secret):
    app = flask.Flask(__name__)
    app.config["DATABASE_PATH"] = db_path
    app.config["MOMO_WEBHOOK_SECRET"] = webhook_secret

    from app.routes.docs import docs_bp
    from app.routes.orders import orders_bp
    from app.routes.webhooks import webhooks_bp

    app.register_blueprint(webhooks_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(docs_bp)

    @app.teardown_appcontext
    def close_db(exception=None):
        db = flask.g.pop("db", None)
        if db is not None:
            db.close()

    return app


def get_db():
    if "db" not in flask.g:
        flask.g.db = get_connection(flask.current_app.config["DATABASE_PATH"])
    return flask.g.db
