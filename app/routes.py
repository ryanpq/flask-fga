from flask import Blueprint, render_template, session, redirect, url_for, request
from urllib.parse import quote_plus, urlencode
from os import environ as env
import json
from app import oauth, db, fga_client
from app.models import User, Group, File, Folder
import uuid
import os
import asyncio
from openfga_sdk.client import OpenFgaClient
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest


main = Blueprint('main', __name__)

async def fga_relate_user_folder(user_uuid,folder_uuid,relation):
    body = ClientWriteRequest(
            writes=[
                    ClientTuple(
                        user=f"user:{user_uuid}",
                        relation=relation,
                        object=f"folder:{folder_uuid}",
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
    createDefaultFolder(user.id)

    return True

def createDefaultFolder(user_id):
    user = User.query.filter_by(id=user_id).first()

    if user is None:
        return False
    
    folder_name = f"{user.name}'s Folder"
    new_uuid = uuid.uuid4()
    folder = Folder(uuid=new_uuid, creator=user.id, name=folder_name, default_folder=True)
    db.session.add(folder)
    db.session.commit()

    #Create owner relationship between user and folder

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(fga_relate_user_folder(user.uuid, new_uuid, "owner"))

    return response






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

@main.route("/")
def home():
    return render_template("home.html", session=session.get('user'), user=session, pretty=json.dumps(session.get("user"), indent=4))