import os
import secrets
from urllib.parse import urlencode
from pathlib import Path
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv
from flask import Flask, redirect, abort, url_for, render_template, flash, session, \
    current_app, request,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user,\
    current_user
import requests
from flask_cors import CORS, cross_origin

dotenv_path = Path('/opt/flask-oauth-example/env/.env')
load_dotenv(dotenv_path=dotenv_path)


app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_URI')
app.config['OAUTH2_PROVIDERS'] = {
    # Google OAuth 2.0 documentation:
    # https://developers.google.com/identity/protocols/oauth2/web-server#httprest
    'google': {
        'client_id': os.environ.get('GOOGLE_CLIENT_ID'),
        'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET'),
        'authorize_url': 'https://accounts.google.com/o/oauth2/auth',
        'token_url': 'https://accounts.google.com/o/oauth2/token',
        'userinfo': {
            'url': 'https://www.googleapis.com/oauth2/v3/userinfo',
            'email': lambda json: json['email'],
        },
        'scopes': ['https://www.googleapis.com/auth/userinfo.email'],
    },

    # GitHub OAuth 2.0 documentation:
    # https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
    'github': {
        'client_id': os.environ.get('GITHUB_CLIENT_ID'),
        'client_secret': os.environ.get('GITHUB_CLIENT_SECRET'),
        'authorize_url': 'https://github.com/login/oauth/authorize',
        'token_url': 'https://github.com/login/oauth/access_token',
        'userinfo': {
            'url': 'https://api.github.com/user/emails',
            'email': lambda json: json[0]['email'],
        },
        'scopes': ['user:email'],
    },

    'facebook': {
        'client_id': os.environ.get('FB_CLIENT_ID'),
        'client_secret': os.environ.get('FB_CLIENT_SECRET'),
        'authorize_url': 'https://www.facebook.com/dialog/oauth',
        'token_url': 'https://graph.facebook.com/oauth/access_token',
        'userinfo': {
            'url': 'https://graph.facebook.com/me?fields=email',
            'email': lambda json: json['email'],
        },
        'scopes': ['email'],
    },
}

db = SQLAlchemy(app)
login = LoginManager(app)
login.login_view = 'index'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(64), nullable=True)


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/unauth')
def unauth():
    logout_user()
    flash('Authorization Failed')
    return redirect(url_for('index'))

@app.route('/login_jwt', methods=['POST'])
def login_jwt():
    code = request.args.get("code")
    # if not employee_is_valid(employee):
    unauth()
    #return redirect(url_for('index'))
    #return redirect("https://cranetrips.com/logout", code=302)

    #return jsonify({ 'accessToken': code}), 200


@app.route('/authorize/<provider>')
def oauth2_authorize(provider):
    if not current_user.is_anonymous:
        #return redirect(url_for('index'))
        return redirect("https://cranetrips.com/logout", code=302)

    provider_data = current_app.config['OAUTH2_PROVIDERS'].get(provider)
    if provider_data is None:
        abort(404)

    # generate a random string for the state parameter
    session['oauth2_state'] = secrets.token_urlsafe(16)

    # create a query string with all the OAuth2 parameters
    if provider == 'facebook':
        qs = urlencode({
            'client_id': provider_data['client_id'],
            'redirect_uri': url_for('oauth2_callback', provider=provider,
                                    _external=True),
            'state': session['oauth2_state'],
        })
    else:
            qs = urlencode({
            'client_id': provider_data['client_id'],
            'redirect_uri': url_for('oauth2_callback', provider=provider,
                                    _external=True),
            'response_type': 'code',
            'scope': ' '.join(provider_data['scopes']),
            'state': session['oauth2_state'],
        })

    # redirect the user to the OAuth2 provider authorization URL    
    return redirect(provider_data['authorize_url'] + '?' + qs)


@app.route('/callback/<provider>')
def oauth2_callback(provider):
    if not current_user.is_anonymous:
        #return redirect(url_for('index'))
        return redirect("http://192.168.1.24:8081/profile" + token, code=302)

    provider_data = current_app.config['OAUTH2_PROVIDERS'].get(provider)
    if provider_data is None:
        abort(404)

    # if there was an authentication error, flash the error messages and exit
    if 'error' in request.args:
        for k, v in request.args.items():
            if k.startswith('error'):
                flash(f'{k}: {v}')
        return redirect(url_for('index'))

    # make sure that the state parameter matches the one we created in the
    # authorization request
    if request.args['state'] != session.get('oauth2_state'):
        abort(401)

    # make sure that the authorization code is present
    if 'code' not in request.args:
        abort(401)

    # exchange the authorization code for an access token
    response = requests.post(provider_data['token_url'], data={
        'client_id': provider_data['client_id'],
        'client_secret': provider_data['client_secret'],
        'code': request.args['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': url_for('oauth2_callback', provider=provider,
                                _external=True),
    }, headers={'Accept': 'application/json'})
    if response.status_code != 200:
        abort(401)
    oauth2_token = response.json().get('access_token')
    if not oauth2_token:
        abort(401)

    # use the access token to get the user's email address
    response = requests.get(provider_data['userinfo']['url'], headers={
        'Authorization': 'Bearer ' + oauth2_token,
        'Accept': 'application/json',
    })
    if response.status_code != 200:
        abort(401)

    email = provider_data['userinfo']['email'](response.json())

    # find or create the user in the database
    user = db.session.scalar(db.select(User).where(User.email == email))
    if user is None:
        user = User(email=email, username=email.split('@')[0])
        db.session.add(user)
        db.session.commit()

    # generate JWT Token
    token = jwt.encode({
        'email': user.email,
        'exp' : datetime.utcnow() + timedelta(minutes = 5)
        }, app.config['SECRET_KEY'])

    print(token)
    login_user(user)
    #return redirect(url_for('index'))
    return redirect("http://192.168.1.24:8081/login?code=" + token, code=302)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
