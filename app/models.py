from . import db
import datetime

# The classes in this file represent our database table and schemas for SQLAlchemy

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.Uuid, unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    image = db.Column(db.String(255))
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255))
    uuid = db.Column(db.Uuid, unique=True, nullable=False)
    creator = db.Column(db.Integer)

class UserGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    group_id = db.Column(db.Integer, nullable=False)

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.Uuid, unique=True, nullable=False)
    folder = db.Column(db.Uuid, nullable=False)
    name = db.Column(db.String(128), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    creator = db.Column(db.Integer)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.Uuid, unique=True, nullable=False)
    creator = db.Column(db.Integer)
    name = db.Column(db.String(128))
    default_folder = db.Column(db.Boolean, default=False)
    parent = db.Column(db.Uuid, nullable=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)
