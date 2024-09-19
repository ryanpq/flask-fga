# Using Fine Grained Authorization in a Python Flask Application

Flask provides a simple framework for rapidly creating web applications in Python.  Using addons like SQLAlchemy and Flask-Login you can save a lot of time and focus your efforts on your application’s core functionality.

In this guide we will build an example application that shows how you can incorporate OpenFGA in your application, allowing you to leverage the benefits of ReBAC authorization with Flask.


## Prerequisites

Before we start, be sure you have the following installed on your development machine:

- **Python 3.x**
- **Flask**
- **SQLAlchemy**
- **Flask-Login**
- **OpenFGA SDK for Python**

Once you have Python installed you can install the necessary packages using `pip3`:

```bash
pip3 install Flask SQLAlchemy Flask-Login openfga_sdk
```

You’ll also need an OpenFGA server instance running.  You can use a remote instance or set up a local instance with Docker with:

```bash
docker run -p 8080:8080 openfga/openfga run
```

## Project Setup

Let's set up the project structure:

```
flask_openfga_tutorial/
├── app/
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── fga.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── index.html
│   │   ├── resource.html
├── config.py
├── model.fga
├── run.py
└── requirements.txt
```

- `app/`: This directory contains our Flask application code including our database model, our route handlers, and our functions that interact with OpenFGA.
- `templates/`: Contains HTML (jinja2) templates for our web interface.
- `config.py`: Configuration settings for Flask and OpenFGA.
- `model.fga`: Our OpenFGA authorization model.
- `run.py`: The entry point for our Flask application.
- `requirements.txt`: Lists our project dependencies.

## Configuring Flask, SQLAlchemy, and Flask-Login

### `config.py`

In our `config.py` we will define the configuration for our Flask application.  We will read sensitive values using `os.getenv()` which allows us to use a .env file in our project directory or from environment variables.

```python
# config.py

import os
from dotenv import load_dotenv

class Config:
    load_dotenv()
    SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///db.sqlite3')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FGA_API_URL = os.getenv('FGA_API_URL', 'http://localhost:8080')
    FGA_STORE_ID = os.getenv('FGA_STORE_ID')
    FGA_MODEL_ID = os.getenv('FGA_MODEL_ID')
```

Replace `'your_secret_key'` with a secure random string in a production environment.

### `app/__init__.py`

Next, we will initialize Flask, SQLAlchemy, and Flask-Login in `app/__init__.py`:

```python
# app/__init__.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    with app.app_context():
        db.create_all()

    return app
```

## Defining the Database Models

### `app/models.py`

We will define the `User` and `Resource` models in `app/models.py`. We'll use extra columns with UUIDs as unique identifiers for users and resources.

```python
# app/models.py

from . import db, login_manager
from flask_login import UserMixin
import uuid

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner = db.relationship('User', backref=db.backref('resources', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
```

- `User`: Represents application users.
- `Resource`: Represents resources owned by users.

## Setting Up the OpenFGA Model

Next we will create our authorization model in the file `model.fga`.  This model will define the types of relationships that can exist between our users and objects:

```plaintext
# model.fga

model
  schema 1.1

type user
  relations
    define owner: [user]

type resource
  relations
    define owner: [user]
    define viewer: owner
```

This model defines two types, `user` and `resource`, and establishes an `owner` relationship. The `viewer` relation is defined to be the same as `owner`, meaning only owners can view the resource.

### Writing the Model to OpenFGA

We will use the OpenFGA CLI to write our new model to our OpenFGA store.  [Learn here](https://openfga.dev/docs/getting-started/cli) how to use the CLI to create a store where you can write your model.  Remember, models are immutable so anytime you make changes you will need to write the updated model and update the model id used in your application.

```bash
fga model write --store-id <YOUR_STORE_ID> --model model.fga
```

Replace `<YOUR_STORE_ID>` with your OpenFGA store ID.

## Setting up the OpenFGA Client

Set up the OpenFGA client in `app/fga.py`:

```python
# app/fga.py

from openfga_sdk.client import ClientConfiguration
from openfga_sdk.sync import OpenFgaClient
from flask import current_app

def get_fga_client():
    config = ClientConfiguration(
        api_url=current_app.config['FGA_API_URL'],
        store_id=current_app.config['FGA_STORE_ID'],
        authorization_model_id=current_app.config['FGA_MODEL_ID'],
    )
    client = OpenFgaClient(config)
    return client
```

This function initializes the OpenFGA client using the configurations from `config.py`.  In our application we use openfga_sdk.sync in order to use the synchronous client.  This lets us avoid issues with SQLAlchemy which does not support asynchronous use.

## Implementing Routes with Flask-Login and OpenFGA

### `app/routes.py`

Next, create the application routes in `app/routes.py`:

```python
# app/routes.py

from flask import Blueprint, request, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, Resource, db
from .fga import get_fga_client
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest, ClientCheckRequest

main = Blueprint('main', __name__)

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('main.register'))

        user = User(
            username=username,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()

        flash('Registration successful. Please log in.')
        return redirect(url_for('main.login'))

    return render_template('register.html')

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password.')
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main.route('/')
@login_required
def index():
    resources = Resource.query.all()
    return render_template('index.html', resources=resources)

@main.route('/create_resource', methods=['POST'])
@login_required
def create_resource():
    resource_name = request.form.get('name')

    resource = Resource(name=resource_name, owner=current_user)
    db.session.add(resource)
    db.session.commit()

    # Create a tuple in OpenFGA
    fga_client = get_fga_client()
    write_request = ClientWriteRequest(
        writes=[
            ClientTuple(
                user=f"user:{current_user.uuid}",
                relation="owner",
                object=f"resource:{resource.uuid}",
            ),
        ],
    )
    fga_client.write(write_request)

    return redirect(url_for('main.resource', resource_uuid=resource.uuid))

@main.route('/resource/<resource_uuid>')
@login_required
def resource(resource_uuid):
    resource = Resource.query.filter_by(uuid=resource_uuid).first()
    if not resource:
        flash('Resource not found.')
        return redirect(url_for('main.index'))

    # Check permission using OpenFGA
    fga_client = get_fga_client()
    check_request = ClientCheckRequest(
        user=f"user:{current_user.uuid}",
        relation="viewer",
        object=f"resource:{resource.uuid}",
    )
    response = fga_client.check(check_request)

    if not response.allowed:
        flash('You do not have permission to view this resource.')
        return redirect(url_for('main.index'))

    return render_template('resource.html', resource=resource)
```

- **User Registration and Login**: Users can register and log in using `register` and `login` routes.
- **Resource Creation**: Users can create resources, and ownership is established by writing a tuple to OpenFGA.
- **Resource Viewing**: Access to resources is controlled by checking permissions with OpenFGA.

## Creating our Web Templates

### Base Template: `templates/base.html`

Create a base template for consistent layout:

```html
<!-- templates/base.html -->

<!doctype html>
<html lang="en">
<head>
    <title>{% block title %}OpenFGA Tutorial{% endblock %}</title>
</head>
<body>
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <ul>
        {% for message in messages %}
          <li>{{ message }}</li>
        {% endfor %}
        </ul>
      {% endif %}
    {% endwith %}

    {% if current_user.is_authenticated %}
        <p>Logged in as {{ current_user.username }} | <a href="{{ url_for('main.logout') }}">Logout</a></p>
    {% endif %}

    {% block content %}{% endblock %}
</body>
</html>
```

### Login Template: `templates/login.html`

This page extends our base template and displays our login form.

```html
<!-- templates/login.html -->

{% extends "base.html" %}
{% block title %}Login{% endblock %}
{% block content %}
<h2>Login</h2>
<form method="POST">
    <input type="text" name="username" placeholder="Username" required><br>
    <input type="password" name="password" placeholder="Password" required><br>
    <button type="submit">Login</button>
</form>
<p>Don't have an account? <a href="{{ url_for('main.register') }}">Register here</a></p>
{% endblock %}
```

### Register Template: `templates/register.html`

This page extends our base template and displays a form that lets users register new accounts.

```html
<!-- templates/register.html -->

{% extends "base.html" %}
{% block title %}Register{% endblock %}
{% block content %}
<h2>Register</h2>
<form method="POST">
    <input type="text" name="username" placeholder="Username" required><br>
    <input type="password" name="password" placeholder="Password" required><br>
    <button type="submit">Register</button>
</form>
<p>Already have an account? <a href="{{ url_for('main.login') }}">Login here</a></p>
{% endblock %}
```

### Index Template: `templates/index.html`

This page extends our base template and provides the UI elements for the main page of our application.

```html
<!-- templates/index.html -->

{% extends "base.html" %}
{% block title %}Home{% endblock %}
{% block content %}
<h2>Welcome, {{ current_user.username }}</h2>

<h3>Create a Resource</h3>
<form method="POST" action="{{ url_for('main.create_resource') }}">
    <input type="text" name="name" placeholder="Resource Name" required>
    <button type="submit">Create</button>
</form>

<h3>Your Resources</h3>
<ul>
    {% for resource in resources %}
        <li><a href="{{ url_for('main.resource', resource_uuid=resource.uuid) }}">{{ resource.name }}</a></li>
    {% else %}
        <li>No resources available.</li>
    {% endfor %}
</ul>
{% endblock %}
```

### Resource Template: `templates/resource.html`

This page extends our base template and displays a list of resources a user has access to.

```html
<!-- templates/resource.html -->

{% extends "base.html" %}
{% block title %}Resource Details{% endblock %}
{% block content %}
<h2>Resource: {{ resource.name }}</h2>
<p>Owned by: {{ resource.owner.username }}</p>
<a href="{{ url_for('main.index') }}">Back to Home</a>
{% endblock %}
```

## Running the Application

### `run.py`

Finally we will create our `run.py` which we will call in order to run the Flask application:

```python
# run.py

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
```

## Testing the Application

### 1. Set up our .env

Our application expects several variables to be set as environment variables or in a .env file in our project directory.  For this example we will create a .env file with the following content:

```plaintext
SECRET_KEY="your_secret_key"
DATABASE_URL="sqlite:///db.sqlite3"
FGA_API_URL="http://localhost:8080"
FGA_STORE_ID="your fga store id"
FGA_MODEL_ID="your fga model id"

```

- SECRET_KEY: If you set a default secret key in your config.py you don't have to include it here.
- DATABSE_URL: In our example we are using SQLite but you can also use a MySQL or PostgreSQL connection string.
- FGA_API_URL: The URL to connect to your OpenFGA instance.  The example above assumes you are running OpenFGA in Docker locally using the command provided earlier.
- FGA_STORE_ID: This is the store id that was returned when you created a store in your OpenFGA instance.
- FGA_MODEL_ID:  This is the model id that was returned when you ran `fga write` to write your model.

### Run the Flask App

Start the application:

```bash
python run.py
```

### Register a User

- Open your browser and navigate to `http://127.0.0.1:5000/`.
- Click on "Register here" and create a new user account.

### Log In

- Log in with your new credentials.

### Create a Resource

- After logging in, create a resource by entering a name and clicking "Create".
- The resource will be added to the database, and an ownership tuple will be written to OpenFGA.

### View the Resource

- Click on the resource name to view its details.
- OpenFGA checks whether you have permission to view the resource based on the `viewer` relation.

### Test Access Control

- Log out and register a new user.
- Try to access the resource created by the first user by entering its URL directly.
- You should receive a message stating you do not have permission to view the resource.

## Next Steps

This guide presented a basic example of how OpenFGA can be used within a Python Flask application to manage authorization and access to resources.  You can find a more detailed example application that implements a web application allowing users to share text files and folders and covers topics including parent child relatinoships and sharing resources with others [in this project](#).

For more detailed information about using OpenFGA, check out the [OpenFGA documentation](https://openfga.dev/docs/getting-started) and explore how you can leverage fine-grained authorization in your applications.


