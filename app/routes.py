from flask import Blueprint, render_template, session, redirect, url_for, request
from urllib.parse import quote_plus, urlencode
from os import environ as env
import json
from app import oauth, db
from app.models import User, Group, File, Folder
import uuid
import os
import asyncio
from openfga_sdk.client import OpenFgaClient, ClientConfiguration
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest


main = Blueprint('main', __name__)

fga_client = None

async def initialize_fga_client():
    print("Initializing OpenFGA Client SDK")
    configuration = ClientConfiguration(
        api_url = os.getenv('FGA_API_URL'), 
        store_id = os.getenv('FGA_STORE_ID'), 
        authorization_model_id = os.getenv('FGA_MODEL_ID'), 
    )

    global fga_client
    fga_client = OpenFgaClient(configuration)
    await fga_client.read_authorization_models()
    print("FGA Client initialized.")

async def fga_relate_user_object(user_uuid,folder_uuid,object_type,relation):

    if fga_client is None:
        await initialize_fga_client()

    body = ClientWriteRequest(
            writes=[
                    ClientTuple(
                        user=f"user:{user_uuid}",
                        relation=relation,
                        object=f"{object_type}:{folder_uuid}",
                    ),
            ],
    )
    response = await fga_client.write(body)
    return response


def loadSession(email):
    print(f"Loading User Info from database for {email}")
    user = User.query.filter_by(email=email).first()

    if user is None:
        return False
    
    session["user_id"] = user.id
    session["uuid"] = user.uuid
    session["name"] = user.name
    session["image"] = user.image

    return True

def registerUser(user_info):
    email = user_info['email']
    name = user_info['name']
    image = user_info['picture']
    
    new_uuid = uuid.uuid4()
    print(f"Registering New User {new_uuid} in Database")

    user = User(email=email, name=name, uuid=new_uuid, image=image)
    db.session.add(user)
    db.session.commit()
    print("User Registered in database")

    #Create Default Folder for new user
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(createDefaultFolder(user.id))
    
    if result is True:
        print("default folder created")
    else:
        print("Error creating default folder")

    return True

async def createDefaultFolder(user_id):
    user = User.query.filter_by(id=user_id).first()

    if user is None:
        return False
    
    folder_name = f"{user.name}'s Folder"
    new_uuid = uuid.uuid4()
    folder = Folder(uuid=new_uuid, creator=user.id, name=folder_name, default_folder=True)
    db.session.add(folder)
    db.session.commit()

    await fga_relate_user_object(user.uuid, new_uuid, "folder", "owner")
    

    return True






@main.route("/login")
def login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("main.callback", _external=True)
    )

@main.route("/callback", methods=["GET", "POST"])
def callback():
    try:
        token = oauth.auth0.authorize_access_token()
        print(f"TOKEN: {token}\n\n\n")
        session["user"] = token

        user_info = token['userinfo']
        

        user = User.query.filter_by(email=user_info['email']).first()
        if user is None:
            registerUser(user_info)
        else:
            print("User is already registered.")

        loadSession(user_info['email'])

    except Exception as e:
        print(f"Error: {e}\n\n")
        return redirect(url_for("main.home"))
    return redirect(url_for("main.home"))

@main.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + env.get("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("main.home", _external=True),
                "client_id": env.get("AUTH0_CLIENT_ID"),
            },
            quote_via=quote_plus,
        )
    )

@main.route("/api/list/<str:folder_uuid>")
def list_directory():
    print("Directory List Request")
    

@main.route("/")
def home():
    if session:
        # If a user is authenticated, fetch their default folder
        user_id = session.get('user_id')
        user_folder = Folder.query.filter_by(creator=user_id, default_folder=True).first()
    else:
        user_folder = None

    return render_template("home.html", session=session.get('user'),pwd=user_folder, user=session, pretty=json.dumps(session.get("user"), indent=4))