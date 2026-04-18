import os

from flask import Flask, render_template
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from config import Config
from db import initialize_mongo
from models.user_model import UserModel
from routes.auth import auth_bp
from routes.ai_core import ai_bp
from routes.candidate import candidate_bp, comparator
from routes.recruiter import recruiter_bp
from utils.helpers import active_role

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    initialize_mongo(app)

    csrf.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(recruiter_bp)
    app.add_url_rule("/comparator", endpoint="comparator", view_func=comparator, methods=["GET"])

    with app.app_context():
        UserModel.create_indexes()

    @app.context_processor
    def inject_globals():
        return {"active_role": active_role(current_user if current_user.is_authenticated else None)}

    @app.route("/")
    def landing():
        return render_template("landing.html")

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/error.html", code=404, title="Page not found", message="The page you requested could not be found."), 404

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/error.html", code=403, title="Forbidden", message="You do not have access to this page."), 403

    @app.errorhandler(413)
    def too_large(error):
        return render_template("errors/error.html", code=413, title="Upload too large", message="Files must be smaller than 5 MB."), 413

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/error.html", code=500, title="Server error", message="Something unexpected happened. Please try again."), 500

    return app


@login_manager.user_loader
def load_user(user_id):
    return UserModel.get_by_id(user_id)


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
