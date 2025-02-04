import os
import secrets
from urllib.parse import urlencode
from pathlib import Path
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv
from flask_api import status
from flask import Flask, redirect, abort, url_for, render_template, flash, session, \
    current_app, request,jsonify,Response,make_response
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_login import LoginManager, UserMixin, login_user, logout_user,\
    current_user
import requests
from flask_cors import CORS, cross_origin
from dataclasses import dataclass
from functools import wraps
from passlib.hash import sha256_crypt

dotenv_path = Path('/opt/flask-oauth-example/env/.env')
load_dotenv(dotenv_path=dotenv_path)


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_URI')
db = SQLAlchemy(app)
ma = Marshmallow(app)
CORS(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'

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
}

login = LoginManager(app)
login.login_view = 'index'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(64), nullable=True)
    token = db.Column(db.String(2000), nullable=True)
    oauth = db.Column(db.Boolean, nullable=False)
    password = db.Column(db.String(256), nullable=True)          

@dataclass
class Trip(db.Model):
    __tablename__ = 'trips'
    id = db.Column(db.Integer, primary_key=True)
    trip_name = db.Column(db.String(255), nullable=False)

class TripSchema(ma.SQLAlchemySchema):
    class Meta:
        model = Trip
    id = ma.auto_field()
    trip_name = ma.auto_field()

@dataclass
class UserTrip(db.Model):
    __tablename__ = 'user_trips'
    id = db.Column(db.Integer, primary_key=True)
    ut_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ut_trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False)
    ut_deleted_date = db.Column(db.DateTime,nullable=True)

class UserTripSchema(ma.SQLAlchemySchema):
    class Meta:
        model = UserTrip
    id = ma.auto_field()
    ut_user_id = ma.auto_field()
    ut_trip_id = ma.auto_field()
    ut_deleted_date = ma.auto_field()


@dataclass
class Lodging(db.Model):
    __tablename__ = 'lodging'
    id = db.Column(db.Integer, primary_key=True)
    lodg_name = db.Column(db.String(255), nullable=False)
    lodg_beds = db.Column(db.Integer, nullable=False)
    lodg_bedrooms = db.Column(db.Integer,nullable=False)
    lodge_price_per_day = db.Column(db.Float,nullable=False)
    lodge_link = db.Column(db.String(2000), nullable=True)

class LodgingSchema(ma.SQLAlchemySchema):
    class Meta:
        model = Lodging
    id = ma.auto_field()
    lodg_name = ma.auto_field()
    lodg_beds = ma.auto_field()
    lodg_bedrooms = ma.auto_field()
    lodge_price_per_day = ma.auto_field()
    lodge_link = ma.auto_field()

@dataclass
class trip_lodging(db.Model):
    __tablename__ = 'trip_lodging'
    id = db.Column(db.Integer, primary_key=True)
    tl_trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False)
    tl_lodge_id = db.Column(db.Integer, db.ForeignKey('lodging.id'), nullable=False)
    tl_deleted_date = db.Column(db.DateTime,nullable=True)

class TripLodgingSchema(ma.SQLAlchemySchema):
    class Meta:
        model = trip_lodging
    id = ma.auto_field()
    tl_trip_id = ma.auto_field()
    tl_lodge_id = ma.auto_field()
    tl_deleted_date = ma.auto_field()

def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = None
        # ensure the jwt-token is passed with the headers
        if 'Authorization' in request.headers:
            bearer = request.headers.get('Authorization')    # Bearer YourTokenHere
            token = bearer.split()[1]  # YourTokenHere
            print(token)
        if not token: # throw error if no token provided
            return make_response(jsonify({"message": "A valid token is missing!"}), 401)
        try:
           # decode the token to obtain user public_id
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            print(data)
            current_user = db.session.scalar(db.select(User).where(User.token == token))
            if current_user is None:
                return make_response(jsonify({"message": "Invalid token!"}), 401)
            print(current_user)
        except Exception as ex:
            print(ex)
            return make_response(jsonify({"message": "Invalid token!"}), 401)
        return f(*args, **kwargs)
    return decorator

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.')
    #return redirect(url_for('index'))
    return redirect("https://cranetrips.com/login", code=302)


@app.route('/unauth')
def unauth():
    logout_user()
    flash('Authorization Failed')
    return redirect(url_for('index'))

@app.route('/trips', methods = ['GET'])
@token_required
def trips():
    trips = Trip.query.all()
    trips_schema = TripSchema(many=True)
    print (len(trips))

    return jsonify(trips_schema.dump(trips))

@app.route('/lodging', methods = ['GET'])
@token_required
def lodging():
    lodging = Lodging.query.all()
    LodgingSchema = LodgingSchema(many=True)
    print (len(lodging))

    return jsonify(LodgingSchema.dump(lodging))

@app.route('/login', methods=['POST'])
def login():
    username = request.args.get("username")
    password = request.args.get("password")

    user = db.session.scalar(db.select(User).where(User.username == username))

    if user is None:
        return Response('Unauthorized', 401)
    else:
        if (sha256_crypt.verify(password, user.password)):
            # generate JWT Token
            token = jwt.encode({
                'email': user.email,
                'exp' : datetime.utcnow() + timedelta(hours = 12)
                }, app.config['SECRET_KEY'])
            user.token = token
            db.session.commit()
            return jsonify({ 'accessToken': token}), 200
        else:
            return Response('Unauthorized', 401)      

@app.route('/login_jwt', methods=['POST'])
def login_jwt():
    code = request.args.get("code")

    user = db.session.scalar(db.select(User).where(User.token == code))
    if user is None:
        unauth()   
        return redirect("https://identity.cranetrips.com/logout", code=302)
    else:
        data = jwt.decode(code, app.config['SECRET_KEY'],algorithms=['HS256'])
        if (data):
            return jsonify({ 'accessToken': code}), 200
        else:
            abort(401)

@app.route('/signup', methods=['POST'])
def signup():

    username = request.args.get("username")
    email = request.args.get("email")

    password = sha256_crypt.encrypt(request.args.get("password"))
    
    user = db.session.scalar(db.select(User).where(User.email == email))
    
    if user is None:

        # generate JWT Token
        token = jwt.encode({
        'email': email,
        'exp' : datetime.utcnow() + timedelta(hours = 12)
        }, app.config['SECRET_KEY'])

        user = User(email=email,username=username,password=password,token=token,oauth=False)
        db.session.add(user)
        db.session.commit()
        resp = Response('', 200)
        return resp
    else:
        abort(500)

@app.route('/authorize/<provider>')
def oauth2_authorize(provider):
    if not current_user.is_anonymous:
        #return redirect(url_for('index'))
        return redirect("https://identity.cranetrips.com/unauth", code=302)

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
        return redirect("https://cranetrips.com" + token, code=302)

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
        user = User(email=email, username=email.split('@')[0],oauth=True)
        db.session.add(user)
        db.session.commit()

    # generate JWT Token
    token = jwt.encode({
        'email': user.email,
        'exp' : datetime.utcnow() + timedelta(hours = 12)
        }, app.config['SECRET_KEY'])

    user.token = token
    db.session.commit()

    login_user(user)
    #return redirect(url_for('index'))
    return redirect("https://cranetrips.com/login?code=" + token, code=302)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
