from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
import asyncio
from openfga_sdk.client import ClientConfiguration, OpenFgaClient


# Load .env
load_dotenv()

# init sqlalchemy
db = SQLAlchemy()
oauth = OAuth()
fga_client = None

async def initialize_fga_client():
    configuration = ClientConfiguration(
        api_url = os.getenv('FGA_API_URL'), # required, e.g. https://api.fga.example
        store_id = os.getenv('FGA_STORE_ID'), # optional, not needed for `CreateStore` and `ListStores`, required before calling for all other methods
        authorization_model_id = os.getenv('FGA_MODEL_ID'), # Optional, can be overridden per request
    )

    global fga_client
    async with OpenFgaClient(configuration) as fga_client:
        api_response = await fga_client.read_authorization_models()
        await fga_client.close()

def create_app():
    app = Flask(__name__)

    app.config.from_object('config.Config')
    db.init_app(app)

    oauth.init_app(app)


    oauth.register(
        "auth0",
        client_id=os.getenv("AUTH0_CLIENT_ID"),
        client_secret=os.getenv("AUTHO_CLIENT_SECRET"),
        client_kwargs={
            "scope":"openid profile email",
        },
        server_metadata_url=f'https://{os.getenv("AUTH0_DOMAIN")}/.well-known/openid-configuration'
    )

    

    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    with app.app_context():
        db.create_all()

    asyncio.run(initialize_fga_client())

    return app

__all__ = ['oauth', 'fga_client']