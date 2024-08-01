from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
import asyncio



# Load .env for configuration values
load_dotenv()

# init sqlalchemy and OAuth libs
db = SQLAlchemy()
oauth = OAuth()


def create_app():
    app = Flask(__name__)

    app.config.from_object('config.Config')
    db.init_app(app)

    oauth.init_app(app)

    # Configure and initialize the Auth0 Client
    oauth.register(
        "auth0",
        client_id=os.getenv("AUTH0_CLIENT_ID"),
        client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
        client_kwargs={
            "scope":"openid profile email",
        },
        server_metadata_url=f'https://{os.getenv("AUTH0_DOMAIN")}/.well-known/openid-configuration'
    )

    
    # Register the blueprint.  This app is configured to use blueprints but only includes a single blueprint
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Create our database schema if it doesn't exist
    with app.app_context():
        db.create_all()

    

    return app

__all__ = ['oauth']