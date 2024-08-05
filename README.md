# flask-fga - An example OpenFGA project using Python-Flask

This project was created as a learning exercise to gain familiarity with [OpenFGA](https://openfga.dev). It provides a basic multi-user environment where users can create folders and text files, create and add users to groups, and share files and folders with other users and groups. This is not a production ready codebase and is intended as a learning aid and starting point to improve and build on.  It provides an example implementation of OpenFGA with Python-Flask and SQLAlchemy.  

## Components

### Flask
Flask is a lightweight WSGI web application framework. It is designed to make getting started quick and easy, with the ability to scale up to complex applications. 

### Python-dotenv
Python-dotenv reads key-value pairs from a .env file and can set them as environment variables. It is used in this project to store sensitive variables such as the OpenFGA connection details and store id as well as the Auth0 credentials.

### authlib
Python library in building OAuth and OpenID Connect servers.  Used in this example to utilize Auth0 services but easily adaptable for other OAuth or OpenID Connect services.

### requests
Requests is a simple, yet elegant, HTTP library for Python. Required along with autlib to interact with the Auth0 authentication service.

### SQLAlchemy
SQLAlchemy is the Python SQL toolkit and Object Relational Mapper that gives application developers the full power and flexibility of SQL. SQLAlchemy provides a full suite of well known enterprise-level persistence patterns, designed for efficient and high-performing database access, adapted into a simple and Pythonic domain language.

### Flask-SQLAlchemy
Flask-SQLAlchemy is an extension for Flask that adds support for SQLAlchemy to your application.

### openfga_sdk
OpenFGA is an open source Fine-Grained Authorization solution inspired by Google's Zanzibar paper.

## Authentication

Auth0 is used for authentication for simplicity but can easily be swapped out for another authentication solution.  Auth0 is initialized in app/__init__.py and utilized in app/routes.py in the route handlers for `/login`, `/logout`, and `/callback`.  The `loadSession()` function uses the information returned during authentication to set session variables which are used throughout the rest of the app and the `registerUser()` function is used to create a new user in the database after they are first authenticated.

## Database

This project uses the Flask SQLAlchemy library to simplify interactions with the application database and allow flexibility in the database solution used.  This project has been tested with sqlite but should be compatible with MySQL or PostgreSQL though minor tweaks to app/models.py could be required if errors are encountered.

## OpenFGA 

This project was created as an example of the capabilities of OpenFGA you can learn more about OpenFGA here.

### Synchronous Mode

Due to limitations using SQLAlchemy in asynchronous functions this app uses OpenFGA in synchronous mode which varies from the examples shown in the official OpenFGA documentation at openfga.dev.  You can learn more about using openfga_sdk in synchronous mode here.

# Installation and Setup

## Install OpenFGA
If you are using an existing OpenFGA server instance or SaaS service you can skip this step.  Using Docker locally is recommended as the simplest self-hosted option to get started with this project.  Follow the instructions found in [this guide](https://openfga.dev/docs/getting-started/setup-openfga/docker) to run OpenFGA in Docker. 

### Note
Because the OpenFGA Playground uses the same default port as Python-Flask you will need to modify the docker run command provided in the documentation

Instead of:
`docker run -p 8080:8080 -p 8081:8081 -p 3000:3000 openfga/openfga run`

You will use:
`docker run -p 8080:8080 -p 8081:8081 -p 3000:3001 openfga/openfga run`

This will expose the playground service on port 3001 instead of 3000 to prevent a conflict.

## Set up your OpenFGA Store and Model
Before you can use this app you will need to create a store in your OpenFGA instance and create the model used by this app. 

### Using the OpenFGA Playground
By default your OpenFGA instance will allow you to manage your stores and models through a browser using the OpenFGA Playground UI.  The playground can be accessed (when running OpenFGA locally) at `http://localhost:3001/playground`.  In the playground, create a new store.  Then copy the content of `model.fga` into the model view and save it.  

Once you have saved your model you can copy the store id and model id that were created for it.  These can be found in the menu in the top right corner of the page. You will need these when configuring the app.

### Using the OpenFGA CLI
You can also use the OpenFGA CLI client to connect with your OpenFGA instance and create your store and model.  You can learn more about the OpenFGA CLI [here](https://openfga.dev/docs/getting-started/cli).  If you are running OpenFGA locally it's default configuration will connect with your local instance.  If you are using a remote FGA service you will need to configure the client with your credentials and connection details before you can proceed.

From this project's main directory run

`fga store create --model model.fga`

You will receive a response that looks like this:

```
{
  "store": {
    "created_at":"2024-02-09T23:20:28.637533296Z",
    "id":"01HP82R96XEJX1Q9YWA9XRQ4PM",
    "name":"docs",
    "updated_at":"2024-02-09T23:20:28.637533296Z"
  },
  "model": {
    "authorization_model_id":"01HP82R97B448K89R45PW7NXD8"
  }
}
```

The "id" in the first section is your `Store ID` and your `Model ID` is the value in the "model" section.  Save these values as you will need them to configure the application.

## Configure Authentication
This app was built using Auth0 for authentication but uses standard librarires for OAuth so modifying it to use another provider should not be overly complicated.  For simplicity this guide will only cover the use of Auth0.

### Create an Auth0 Account
If you do not have an Auth0 account, create one [here](https://auth0.com/signup).  This app can be used with a free plan.

### Configure an application
Use the interactive selector to create a new Auth0 application.

#### Application Type
For Application Type select "Single Page Application"

#### Allowed Callback URLs
Enter `http://localhost:3000/callback` in "Allowed Callback URLs"

#### Allowed Logout URLs
Enter `http://localhost:3000/` in "Allowed Logout URLs"

#### Allowed Web Origins
Enter `http://localhost:3000` in "Allowed Web Origins"

By default your app will have two "Connections" enabled for providing user authentication data.

- google-oauth2 - This option allows users to log in with Google.  There is no need to configure user accounts with this option

- Username-Password-Authentication - This option allows you to create user accounts in the Auth0 dashboard by specifying usernames and passwords

### Collect required credentials
From your application's page in the Auth0 Dashboard copy your app's `Domain`, `Client ID`, and `Client Secret`

## Create a Python Virtual Environment (optional)
While not required it is recommended to use a virtual environment for your Python apps.  

From the main directory for this app run:

`python3 -m venv venv`

Then you can begin working in your virutal environment with:

Linux/Mac:
`source venv/bin/activate`

Windows:
`venv\Scripts\activate.bat`

## Install prerequisites
Install the required python prerequisites with:

`pip3 install -r requirements.txt`

## Configure your application
Next, make a copy of `env.example` named `.env` in the main directory of the app.  Open this file and fill in the needed values.

```
AUTH0_CLIENT_ID=<Client ID from your Auth0 App>
AUTH0_CLIENT_SECRET=<Client Secret from your Auth0 App>
AUTH0_DOMAIN=<Domain from your Auth0 App>
APP_SECRET_KEY=<A unique string used as your app's secret key>
SQLALCHEMY_DATABASE_URI=sqlite:///db.sqlite3
PORT=3000
FGA_API_URL=http://localhost:8080
FGA_STORE_ID=<The Store ID you got from OpenFGA>
FGA_MODEL_ID=<The Model ID from the model you created in OpenFGA>
```

## Launch the app
Now that everything is set up you can launch your app.  From the main directory of the app run `python3 run.py`

You can now access your app at `http://localhost:3000/` and log in either with a Google account or with a user and password combination you created in the Auth0 dashboard.