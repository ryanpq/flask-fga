from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from urllib.parse import quote_plus, urlencode
from os import environ as env
import json
from app import oauth, db
from app.models import User, Group, File, Folder, UserGroup
import uuid
import os
import asyncio
from openfga_sdk.client import ClientConfiguration
from openfga_sdk.sync import OpenFgaClient
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest, ClientCheckRequest, ClientListObjectsRequest
from functools import wraps
import datetime


main = Blueprint('main', __name__)

fga_client = None

def initialize_fga_client():
    print("Initializing OpenFGA Client SDK")
    configuration = ClientConfiguration(
        api_url = os.getenv('FGA_API_URL'), 
        store_id = os.getenv('FGA_STORE_ID'), 
        authorization_model_id = os.getenv('FGA_MODEL_ID'), 
    )

    global fga_client
    fga_client = OpenFgaClient(configuration)
    fga_client.read_authorization_models()
    print("FGA Client initialized.")

def fga_relate_user_object(user_uuid,object_uuid,object_type,relation):

    if fga_client is None:
        initialize_fga_client()

    body = ClientWriteRequest(
            writes=[
                    ClientTuple(
                        user=f"user:{user_uuid}",
                        relation=relation,
                        object=f"{object_type}:{object_uuid}",
                    ),
            ],
    )
    response = fga_client.write(body)
    return response

def fga_delete_user_tuple(user_uuid,object_uuid,object_type,relation):
    if fga_client is None:
        initialize_fga_client()

    body = ClientWriteRequest(
            deletes=[
                    ClientTuple(
                        user=f"user:{user_uuid}",
                        relation=relation,
                        object=f"{object_type}:{object_uuid}",
                    ),
            ],
    )
    response = fga_client.write(body)
    return response

def fga_relate_objects(object1_type,object1_uuid,object2_type,object2_uuid,relation):

    if fga_client is None:
        initialize_fga_client()

    body = ClientWriteRequest(
            writes=[
                    ClientTuple(
                        user=f"{object1_type}:{object1_uuid}",
                        relation=relation,
                        object=f"{object2_type}:{object2_uuid}",
                    ),
            ],
    )
    response = fga_client.write(body)
    return response

def fga_delete_object_tuple(object1_type,object1_uuid,object2_type,object2_uuid,relation):

    if fga_client is None:
        initialize_fga_client()

    body = ClientWriteRequest(
            deletes=[
                    ClientTuple(
                        user=f"{object1_type}:{object1_uuid}",
                        relation=relation,
                        object=f"{object2_type}:{object2_uuid}",
                    ),
            ],
    )
    response = fga_client.write(body)
    return response

def fga_check_user_access(user_uuid,action,object_type,object_uuid):
    if fga_client is None:
        initialize_fga_client()

    print(f"Checking user: {user_uuid} for {action} permission on the {object_type} {object_uuid}")

    body = ClientCheckRequest(
        user=f"user:{user_uuid}",
        relation=action,
        object=f"{object_type}:{object_uuid}",
    )

    response = fga_client.check(body)
    return response.allowed

def fga_list_objects(user_uuid,action,object_type):
    if fga_client is None:
        initialize_fga_client()

    print(f"Getting objects of type {object_type} where user {user_uuid} has a {action} relationship.")

    body = ClientListObjectsRequest(
        user=f"user:{user_uuid}",
        relation=action,
        type=object_type,
    )

    response = fga_client.list_objects(body)

    return response.objects

def relateUserObject(user_uuid,object_uuid,object_type,relation):
    
    result = fga_relate_user_object(user_uuid,object_uuid,object_type,relation)

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

    home_folder = Folder.query.filter_by(creator=user.id,default_folder=True).first()

    session["home_folder"] = home_folder.uuid
    session["home_folder_name"] = home_folder.name
    session['pwd'] = home_folder.uuid

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
    folder_id = createDefaultFolder(user.id)

    createDefaultFile(user.id,folder_id)

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

    fga_relate_user_object(user.uuid, new_uuid, "folder", "owner")
    

    return folder.id

def createDefaultFile(user_id, folder_id):
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

    fga_relate_user_object(user.uuid, new_uuid, "file", "owner")

    return True

def createNewFolder(parent_uuid,name,user_id):
    user = User.query.filter_by(id=user_id).first()

    if user is None:
        return False
    
    new_uuid = uuid.uuid4()
    folder = Folder(uuid=new_uuid, parent=parent_uuid, default_folder=False, creator=user_id, name=name)
    db.session.add(folder)
    db.session.commit()

    print(f"New folder {name} created, creating new authorization tuples")

    fga_relate_user_object(user.uuid, new_uuid, "folder", "owner")

    print(f"Created ownership.  Now creating parent-child relationship between {parent_uuid} and {new_uuid}")

    fga_relate_objects("folder", parent_uuid, "folder", new_uuid, "parent")

    return True

def createNewFile(parent_uuid, name, user_id, content):
    user = User.query.filter_by(id=user_id).first()

    if user is None:
        return False
    
    new_uuid = uuid.uuid4()

    print(f"Creating a new file named {name} in directory {parent_uuid} for user_id {user_id}")

    file = File(uuid=new_uuid, folder=parent_uuid, creator=user_id, name=name, text_content=content)
    db.session.add(file)
    db.session.commit()

    print(f"New File {name} created, creating new authorization tuples")

    fga_relate_user_object(user.uuid, new_uuid, "file", "owner")
    fga_relate_objects("folder", parent_uuid, "file", new_uuid, "parent")

    return new_uuid

def createNewGroup(name, user_uuid):
    user = User.query.filter_by(uuid=user_uuid).first()

    if user is None:
        return False
    
    new_uuid = uuid.uuid4()

    # Create Group db entry
    group = Group(uuid=new_uuid,creator=user.id, name=name)
    db.session.add(group)
    db.session.commit()

    # Make user creator of group
    assoc = UserGroup(user_id=user.id, group_id=group.id)
    db.session.add(assoc)
    db.session.commit()

    # Create FGA Tuple
    fga_relate_user_object(user_uuid,new_uuid,"group","owner")

    return new_uuid

# Route Handers


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

@main.route("/api/list/<folder_uuid>")
@api_require_auth
def list_directory(folder_uuid):
    folder_uuid_u = uuid.UUID(folder_uuid)
    print(f"Directory List Request uuid: {folder_uuid}")
    user_uuid = session['uuid']
    pwd = Folder.query.filter_by(uuid=folder_uuid_u).first()
    print("Got Folder Info")
    child_folders = Folder.query.filter_by(parent=pwd.uuid).all()
    print("Got Child Folders")
    child_files = File.query.filter_by(folder=pwd.uuid).all()
    print("Got Child Files")
    folder_objects = []
    sidebar_objects = []

    session["pwd"] = folder_uuid_u

    print("Checking for parent folder")
    if pwd.parent is not None:
        parent_dir = Folder.query.filter_by(uuid=pwd.parent).first()
        if fga_check_user_access(user_uuid, "viewer", "folder", parent_dir.uuid):
            folder_objects.append({
                "uuid": parent_dir.uuid,
                "name": "..",
                "type": "folder"
            })
        

    print("Checking child folder permissions")
    for folder in child_folders:
        if fga_check_user_access(user_uuid, "viewer", "folder", folder.uuid):
            folder_objects.append({
                "uuid": folder.uuid,
                "name": folder.name,
                "type": "folder"
            })
    
    print("Checking child file permissions")
    for file in child_files:
        print(f"Found File {file.name}")
        if fga_check_user_access(user_uuid, "can_read", "file", file.uuid):
            print(f"Access to file {file.name} granted")
            folder_objects.append({
                "uuid": file.uuid,
                "name": file.name,
                "type": "file"
            })
        else:
            print(f"Access to file {file.name} denied")

    print("Checking for folders shared with this user")

    folders = fga_list_objects(user_uuid,"viewer","folder")
    print(f"Shared Folders:\n{folders}\n---")
    for shared_folder in folders:
        folder_uuid = shared_folder.split("folder:")[1]
        folder_uuid_u = uuid.UUID(folder_uuid)
        folder = Folder.query.filter_by(uuid=folder_uuid_u).first()
        if folder.creator is not session['user_id']:
            sidebar_objects.append({
                "uuid": folder_uuid,
                "name": folder.name,
                "type": "folder"
            })

    client_response = {
        "folder_uuid": str(pwd.uuid),
        "folder_name": pwd.name,
        "contents": folder_objects,
        "sidebar" : sidebar_objects
    }
    return jsonify(client_response)

@main.route("/api/create_folder/<folder_uuid>", methods=["POST"])
@api_require_auth
def create_folder(folder_uuid):
    name = request.form['name']
    print(f"Creating folder named {name} in uuid: {folder_uuid}")
    folder_uuid_u = uuid.UUID(folder_uuid)
    user_id = session['user_id']
    user_uuid = session['uuid']
    pwd = Folder.query.filter_by(uuid=folder_uuid_u).first()

    if fga_check_user_access(user_uuid, "can_create_file", "folder", folder_uuid):
        createNewFolder(folder_uuid_u,name,user_id)
    else:
        print("Access Denied to create folder")
        return jsonify({'result': 'access denied'}), 403

    return jsonify({'result': 'success'})

@main.route("/api/load_file/<file_uuid>")
@api_require_auth
def load_file(file_uuid):
    user_id = session['user_id']
    user_uuid = session['uuid']
    file_uuid_u = uuid.UUID(file_uuid)

    if fga_check_user_access(user_uuid, "can_read", "file", file_uuid):
        print("User allowed to read file")
        read_allowed = True
        file = File.query.filter_by(uuid=file_uuid_u).first()
        if fga_check_user_access(user_uuid, "can_write", "file", file_uuid):
            print("User allowed to write file")
            write_allowed = True

        else:
            write_allowed = False
        
        client_response = {
            "authorized": True,
            "read_allowed": read_allowed,
            "write_allowed": write_allowed,
            "file_name": file.name,
            "file_content": file.text_content
        }
        return jsonify(client_response)
    else:
        read_allowed = False
        write_allowed = True

        client_response = {
            "authorized": False,
            "read_allowed": read_allowed,
            "write_allowed": write_allowed,
            "message": "File access not authorized"
        }
        return jsonify(client_response), 403


@main.route("/api/save_file/<file_uuid>", methods=["POST"])
@api_require_auth
def save_file(file_uuid):
    name = request.form['name']
    content = request.form['content']
    user_uuid = session['uuid']
    user_id = session['user_id']
    file_uuid_u = uuid.UUID(file_uuid)

    if fga_check_user_access(user_uuid, "can_write", "file", file_uuid):
        print("Write authorized")
        file = File.query.filter_by(uuid=file_uuid_u).first()
        file.name = name
        file.text_content = content
        file.updated = datetime.datetime.utcnow()
        db.session.commit()
        client_response = {
            "authorized": True,
            "write_allowed": True,
            "result": "success",
            "message": "Changes saved to file"
        }
        return jsonify(client_response)
    else:
        print("User is not authorized to write this file")
        client_response = {
            "authorized": False,
            "write_allowed": False,
            "message": "User is not authorized to write file"
        }
        return jsonify(client_response), 403



@main.route("/api/create_file/<folder_uuid>", methods=["POST"])
@api_require_auth
def create_file(folder_uuid):
    name = request.form['name']
    content = request.form['content']
    print(f"Creating file named {name} in uuid: {folder_uuid}")
    folder_uuid_u = uuid.UUID(folder_uuid)
    user_id = session['user_id']
    user_uuid = session['uuid']
    pwd = Folder.query.filter_by(uuid=folder_uuid_u).first()

    if fga_check_user_access(user_uuid, "can_create_file", "folder", pwd.uuid):
        print(f"User has permission.  Creating new file named {name} in folder {pwd.name}:{folder_uuid}")
        file_uuid = createNewFile(folder_uuid_u, name, user_id, content)
    else:
        print("Access Denied to create a file here"), 403
        return jsonify({'result': 'access denied'})

    return jsonify({'result': 'success', 'uuid': file_uuid })

@main.route("/api/delete_file/<file_uuid>", methods=["POST"])
@api_require_auth
def delete_file(file_uuid):
    file_uuid_u = uuid.UUID(file_uuid)
    user_uuid = session['uuid']

    if fga_check_user_access(user_uuid, "can_write", "file", file_uuid_u):
        print("User authorized with write access can delete file.")
        File.query.filter_by(uuid=file_uuid).delete()
        db.session.commit()
        client_response = {
            "authorized": True,
            "success": True,
            "message": "File Deleted"
        }
        return jsonify(client_response)
    else:
        print("User is not authorized to delete file")
        client_response = {
            "authorized" : False,
            "success": False,
            "message": "User not authorized"
        }
        return jsonify(client_response), 403

@main.route("/api/create_group", methods=["POST"])
@api_require_auth
def create_group():
    group_name = request.form["name"]
    user_uuid = session['uuid']
    user_id = session['user_id']

    group_uuid = createNewGroup(group_name,user_uuid)

    if group_uuid:
        client_response = {
            "status" : "success",
            "message": f"Group {group_name} created with UUID: {group_uuid}"
        }
        return jsonify(client_response)
    else:
        client_response = {
            "status": "error",
            "message": "Failed to create group"
        }
        return jsonify(client_response), 403
    
@main.route("/api/group/<group_uuid>")
@api_require_auth
def get_group(group_uuid):
    user_uuid = session["uuid"]
    group_uuid_u = uuid.UUID(group_uuid)

    if fga_check_user_access(user_uuid,"can_view", "group", group_uuid):
        # User is authorized to view group members
        group = Group.query.filter_by(uuid=group_uuid_u).first()
        members = UserGroup.query.filter_by(group_id=group.id).all()
        if fga_check_user_access(user_uuid, "can_invite", "group", group_uuid):
            can_invite = True
        else:
            can_invite = False

        member_list = []
        member_count = 0

        for member in members:
            group_member = User.query.filter_by(id=member.user_id).first()

            #Check member's access level
            member_level = None
            if fga_check_user_access(group_member.uuid, "member", "group", group_uuid):
                member_level = "member"
            if fga_check_user_access(group_member.uuid, "admin", "group", group_uuid):
                member_level = "admin"
            if fga_check_user_access(group_member.uuid, "owner", "group", group_uuid):
                member_level = "owner"

            if member_level is not None:
                member_list.append({
                    "name" : group_member.name,
                    "uuid": group_member.uuid,
                    "image": group_member.image,
                    "email": group_member.email,
                    "role" : member_level
                })
                member_count += 1
        
        client_response = {
            "result": "success",
            "name" : group.name,
            "can_invite": can_invite,
            "member_count": member_count,
            "members": member_list
        }
        return jsonify(client_response)
    
    else:
        client_response = {
            "result": "Error",
            "message": "Not authorized to view group details"
        }
        return jsonify(client_response), 403
    
@main.route("/api/share/folder/<folder_uuid>", methods=["POST"])
@api_require_auth
def share_folder(folder_uuid):
    print("Folder Share Request")
    user_id = session["user_id"]
    user_uuid = session["uuid"]
    

    subject_uuid = request.form["subject_uuid"]
    subject_type = request.form["subject_type"]

    allow_write = request.form["allow_write"]

    print(f"Allow Write: {allow_write}")

    if fga_check_user_access(user_uuid,"can_share","folder",folder_uuid):
        print("User is authorized to share folder")
        if allow_write == "true":
            relation = "writer"
        else:
            relation = "viewer"

        print(f"Sharing folder {folder_uuid} with {subject_type} {subject_uuid} with relation {relation}")

        if subject_type == "user":
            
            fga_relate_user_object(subject_uuid,folder_uuid,"folder",relation)
        elif subject_type == "group":
            fga_relate_objects("group",subject_uuid,"folder", folder_uuid, relation)
        else:
            client_response = {
            "result": "error",
            "message": "No valid subject type defined"
            }
            return jsonify(client_response), 500

        client_response = {
            "result": "success",
            "message": "Folder shared"
        }
        return jsonify(client_response)


    else:
        client_response = {
            "result": "error",
            "message": "Not authorized to share this folder"
        }
        return jsonify(client_response), 403


@main.route("/api/share/file/<file_uuid>")
@api_require_auth
def share_file(file_uuid):
    print("File Share Request")

@main.route("/api/group/add/<group_uuid>")
@api_require_auth
def group_add_user(group_uuid):
    print("Add user to group request")

@main.route("/api/group/make_admin/<group_uuid>")
@api_require_auth
def group_make_user_admin(group_uuid):
    print("Make user group admin")

@main.route("/api/group/downgrade_user/<group_uuid>")
@api_require_auth
def group_downgrade_user(group_uuid):
    print("Remove group admin privileges from user")

@main.route("/api/group/remove_user/<group_uuid>")
@api_require_auth
def group_remove_user(group_uuid):
    print("Remove user from group")

@main.route("/api/user_autocomplete", methods=["POST"])
@api_require_auth
def user_autocomplete():
    partial = request.form["partial"]
    suggestions = User.query.filter(User.email.startswith(partial)).limit(8)
    matches = []
    match_count = 0
    for user in suggestions:
        matches.append({
            "name": user.name,
            "email": user.email,
            "uuid": user.uuid,
            "image": user.image
        })
        match_count += 1
    client_response = {
        "matches": match_count,
        "users": matches
    }
    return jsonify(client_response)


@main.route("/api/group_autocomplete", methods=["POST"])
@api_require_auth
def group_autocomplete():
    user_uuid = session["uuid"]
    
    partial = request.form["partial"]
    suggestions = Group.query.filter(Group.name.startswith(partial)).limit(8)
    matches = []
    match_count = 0
    for group in suggestions:
        if fga_check_user_access(user_uuid,"can_view","group",group.uuid):
            matches.append({
                "name": group.name,
                "uuid": group.uuid
            })
            match_count += 1
    client_response = {
        "matches": match_count,
        "groups": matches
    }
    return jsonify(client_response)


@main.route("/file/<file_uuid>")
@require_auth
def file_view(file_uuid):
    file_uuid_u = uuid.UUID(file_uuid)
    user_uuid = session.get('uuid')

    if fga_check_user_access(user_uuid, "can_read", "file", file_uuid):
        print("File access authorized")
        file = File.query.filter_by(uuid=file_uuid_u).first()
        creator = User.query.filter_by(id=file.creator).first()

        if fga_check_user_access(user_uuid, "can_write", "file", file_uuid):
            write_allowed = True
        else:
            write_allowed = False

        if fga_check_user_access(user_uuid, "can_share", "file", file_uuid):
            share_allowed = True
        else:
            share_allowed = False

        
        created = datetime.datetime.strftime(file.created, '%d-%b-%Y %H:%M')
        updated = datetime.datetime.strftime(file.updated, '%d-%b-%Y %H:%M')

        client_response = {
            "authorized": True,
            "write_allowed": write_allowed,
            "share_allowed": share_allowed,
            "uuid": file_uuid,
            "name": file.name,
            "content": file.text_content,
            "created": created,
            "modified": updated,
            "creator_name": creator.name,
            "creator_image": creator.image
        }
        return render_template("file.html", user=session, data=client_response)
    else:
        print("Not authorized")
        client_response = {
            "authorized": False,
            "message": "Not authorized to view this file"
        }
        return render_template("file.html", user=session, data=client_response), 403
    
@main.route("/groups")
@require_auth
def groups():
    user_id = session['user_id']
    user_uuid = session['uuid']

    groups = UserGroup.query.filter_by(user_id=user_id)

    users_groups = []
    group_count = 0

    for membership in groups:
        group_id = membership.group_id
        group = Group.query.filter_by(id=group_id).first()

        member_count = UserGroup.query.filter_by(group_id=group_id).count()

        access_level = None
        if fga_check_user_access(user_uuid, "member", "group", group.uuid):
            access_level = "member"

        if fga_check_user_access(user_uuid, "admin", "group", group.uuid):
            access_level = "admin"

        if fga_check_user_access(user_uuid, "owner", "group", group.uuid):
            access_level = "owner"

        if fga_check_user_access(user_uuid, "can_invite", "group", group.uuid):
            can_invite = True 
        else:
            can_invite = False

        if access_level is not None:
            users_groups.append({
                "group_name" : group.name,
                "group_uuid" : group.uuid,
                "member_count": member_count,
                "access_level": access_level,
                "can_invite": can_invite
            })
            group_count += 1

    client_response = {
        "group_count": group_count,
        "groups": users_groups
    }

    return render_template("groups.html", user=session, data=client_response)


    
@main.route("/")
def home():
    if session:
        user_id = session.get('user_id')
        user_uuid = session.get('uuid')
        if not session.get('pwd'):
            # If a user is authenticated, fetch their default folder
            user_folder = Folder.query.filter_by(creator=user_id, default_folder=True).first()
            session['home_folder'] = user_folder.uuid
            session['pwd'] = user_folder.pwd
        else:
            current_directory = session.get('pwd')
            u_type = type(current_directory)
            print(f"Current Folder: {current_directory} Type: {u_type}")
            
            if fga_check_user_access(user_uuid,"viewer","folder", current_directory):
                user_folder = Folder.query.filter_by(uuid=current_directory).first()
            else:
                # If user is not authorized to view the folder, give them their default folder
                user_folder = Folder.query.filter_by(creator=user_id, default_folder=True).first()
                session['home_folder'] = user_folder.uuid
                session['home_folder_name'] = user_folder.name
                session["pwd"] = user_folder.uuid
    else:
        user_folder = None

    return render_template("main.html", session=session.get('user'),pwd=user_folder, user=session, pretty=json.dumps(session.get("user"), indent=4))