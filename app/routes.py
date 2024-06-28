from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from urllib.parse import quote_plus, urlencode
from os import environ as env
import json
from app import oauth, db
from app.models import User, Group, File, Folder
import uuid
import os
import asyncio
from openfga_sdk.client import OpenFgaClient, ClientConfiguration
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest, ClientCheckRequest
from functools import wraps


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

async def fga_relate_user_object(user_uuid,object_uuid,object_type,relation):

    if fga_client is None:
        await initialize_fga_client()

    body = ClientWriteRequest(
            writes=[
                    ClientTuple(
                        user=f"user:{user_uuid}",
                        relation=relation,
                        object=f"{object_type}:{object_uuid}",
                    ),
            ],
    )
    response = await fga_client.write(body)
    return response

async def fga_check_user_access(user_uuid,action,object_type,object_uuid):
    if fga_client is None:
        await initialize_fga_client()

    print(f"Checking user: {user_uuid} for {action} permission on the {object_type} {object_uuid}")

    body = ClientCheckRequest(
        user=f"user:{user_uuid}",
        relation=action,
        object=f"{object_type}:{object_uuid}",
    )

    response = await fga_client.check(body)
    return response.allowed

def checkUserAccess(user_uuid,action,object_type,object_uuid):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(fga_check_user_access(user_uuid,action,object_type,object_uuid))

    return result

def relateUserObject(user_uuid,object_uuid,object_type,relation):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(fga_relate_user_object(user_uuid,object_uuid,object_type,relation))

    return result
    

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

def api_require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"error": "Permission denied - no authenticated user"}), 403
        return f(*args,**kwargs)
    return decorated_function

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

async def registerUser(user_info):
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
    folder_id = await createDefaultFolder(user.id)

    await createDefaultFile(user.id,folder_id)

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
    

    return folder.id

async def createDefaultFile(user_id, folder_id):
    user = User.query.filter_by(id=user_id).first()
    folder = Folder.query.filter_by(id=folder_id).first()

    if user is None or folder is None:
        return False
    
    file_name = "Readme.txt"
    file_content = "Welcome to your folder.  You can create and share text files here."
    new_uuid = uuid.uuid4()

    file = File(uuid=new_uuid, folder=folder.uuid, name=file_name, text_content=file_content, creator=user.id)
    db.session.add(file)
    db.session.commit()

    print("Default file created, updating authorization tuple")

    await fga_relate_user_object(user.uuid, new_uuid, "file", "owner")

    return True




# Route Handers


@main.route("/login")
def login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("main.callback", _external=True)
    )

@main.route("/callback", methods=["GET", "POST"])
def callback():
    async def async_callback():
        try:
            token = oauth.auth0.authorize_access_token()
            print(f"TOKEN: {token}\n\n\n")
            session["user"] = token

            user_info = token['userinfo']
            

            user = User.query.filter_by(email=user_info['email']).first()
            if user is None:
                await registerUser(user_info)
            else:
                print("User is already registered.")

            loadSession(user_info['email'])

        except Exception as e:
            print(f"Error: {e}\n\n")
            return redirect(url_for("main.home"))
        return redirect(url_for("main.home"))
    return asyncio.run(async_callback())

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

@main.route("/api/list/<folder_uuid>")
@api_require_auth
def list_directory(folder_uuid):
    async def async_list_directory(folder_uuid):
        folder_uuid_u = uuid.UUID(folder_uuid)
        print(f"Directory List Request uuid: {folder_uuid}")
        user_uuid = session['uuid']
        pwd = Folder.query.filter_by(uuid=folder_uuid_u).first()
        print("Got Folder Info")
        child_folders = Folder.query.filter_by(parent=pwd.uuid)
        print("Got Child Folders")
        child_files = File.query.filter_by(folder=pwd.uuid)
        print("Got Child Files")
        folder_objects = []

        print("Checking child folder permissions")
        for folder in child_folders:
            if await fga_check_user_access(user_uuid,"can_read", folder.uuid):
                folder_objects.apend({
                    "uuid": folder.uuid,
                    "name": folder.name,
                    "type": "folder"
                })
        
        print("Checking child file permissions")
        for file in child_files:
            if await fga_check_user_access(user_uuid, "can_read", "file", file.uuid):
                folder_objects.append({
                    "uuid": file.uuid,
                    "name": file.name,
                    "type": "file"
                })
        return jsonify(folder_objects)
    return asyncio.run(async_list_directory(folder_uuid))

@main.route("/")
def home():
    if session:
        # If a user is authenticated, fetch their default folder
        user_id = session.get('user_id')
        user_folder = Folder.query.filter_by(creator=user_id, default_folder=True).first()
    else:
        user_folder = None

    return render_template("home.html", session=session.get('user'),pwd=user_folder, user=session, pretty=json.dumps(session.get("user"), indent=4))