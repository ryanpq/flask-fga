from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from urllib.parse import quote_plus, urlencode
from os import environ as env
import json
from app import oauth

main = Blueprint('main', __name__)

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
    return render_template("home.html", session=session.get('user'), pretty=json.dumps(session.get("user"), indent=4))