#!/usr/bin/env python
# To test:
#
# curl -H "Authorization: Key Hu8mXzkPfxB7MCd05FaqJPV9BFaXNE" -XDELETE http://localhost:7000/api/v1/cache/<APP ID>
#
from functools import wraps
from flask import Flask, request, Response, jsonify, session, redirect, url_for, escape, g
from multiprocessing import Pool
import logging
import MySQLdb
import MySQLdb.cursors
import json
import subprocess
import os
import requests
import sys
import datetime
import uuid
import urllib


app = Flask(__name__)

API_KEY = 'knowWhereAPIKEY'
MYSQL_HOSTNAME = 'localhost'
MYSQL_USERNAME = 'root'
MYSQL_PASSWORD = '1'
MYSQL_DATABASE = 'know_where'
ASYNC_POOL = None


# http://stackoverflow.com/questions/16061641/python-logging-split-between-stdout-and-stderr
class InfoFilter(logging.Filter):
    def filter(self, rec):
        return rec.levelno in (logging.DEBUG, logging.INFO)


logger = logging.getLogger(__name__)


def setup_logger():
    ###############################
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    logger.setLevel(logging.DEBUG)

    h1 = logging.StreamHandler(stream=sys.stdout)
    h1.setLevel(logging.DEBUG)
    h1.setFormatter(formatter)
    h1.addFilter(InfoFilter())

    h2 = logging.StreamHandler()
    h2.setLevel(logging.WARNING)
    h2.setFormatter(formatter)

    logger.addHandler(h1)
    logger.addHandler(h2)    
    ###############################


@app.before_request
def before_request():
    g.db = connect_db()
    g.cur = g.db.cursor()


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


def connect_db():
    db = MySQLdb.connect(host=MYSQL_HOSTNAME,
                         user=MYSQL_USERNAME,
                         passwd=MYSQL_PASSWORD,
                         db=MYSQL_DATABASE,
                         cursorclass=MySQLdb.cursors.DictCursor)
    return db


def success(data=""):
    resp = jsonify({
        "success": True,
        "data": data
    })
    return resp


def _error(msg=""):
    resp = jsonify({
        "success": False,
        "msg": msg
    })
    return resp


def check_auth(auth):    
    g.cur.execute("SELECT user_id FROM user_tokens where token = %s and is_valid = 1", (auth,))
    user = g.cur.fetchone()
    if user is not None:
        g.loggedin_user_id = user["user_id"]
        return True


def access_denied():
    """Sends a 401 response"""
    return Response(
        'Could not verify your access level for that URL.\n', 401)


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('auth_token')
        if not auth or not check_auth(auth):
            return access_denied()
        else:
            return f(*args, **kwargs)
    return decorated


@app.route('/api/v1/cache/<app_id>', methods=['GET'])
@requires_auth
def get_cache_status(app_id):
    results = fetch_app_id_data(app_id)
    return jsonify(data=results)


@app.route("/")
def hello():
    resp = Response("Know Where!")
    return resp

#
# @app.errorhandler(Exception)
# def handle_invalid_usage(error):
#     app.logger.error(error)
#     return _error(str(error))


@app.route('/api/v1/user/location', methods=['POST'])
@requires_auth
def update_user_location():
    lat = request.form.get('lat')
    lon = request.form.get('lon')
    radius = request.form.get('radius')

    g.cur.execute("insert into user_location (user_id, lat, lon, radius ) values (%s, %s, %s, %s)", (g.loggedin_user_id, lat, lon, radius))
    g.cur.execute("UPDATE  users SET  lat =  %s, lon = %s WHERE  users.id = %s;", (lat, lon, g.loggedin_user_id))
    g.db.commit()

    return success()

@app.route('/api/v1/user/friends', methods=['POST'])
@requires_auth
def send_friend_request():
    friend_email = request.form.get('friend_email')
    g.cur.execute("SELECT id FROM users where email = %s ", (friend_email))
    friend = g.cur.fetchone()
    if friend is not None :
        g.cur.execute("insert into friends (user_id, friend_id, status, requester_id ) values (%s, %s, %s, %s)", (g.loggedin_user_id, friend["id"], 0, g.loggedin_user_id))
        g.cur.execute("insert into friends (user_id, friend_id, status, requester_id ) values (%s, %s, %s, %s)", ( friend["id"], g.loggedin_user_id, 0, g.loggedin_user_id))
        g.db.commit()
        
        return success()
    else :
        return _error("Requested email hasn't registered yet")


@app.route('/api/v1/user/friends', methods=['GET'])
@requires_auth
def get_friends_list():    
    g.cur.execute("SELECT friends.friend_id as friend_id, friends.id as friend_request_id,friends.requester_id as requester_id, friends.status as status, users.email as friend_email, users.first_name as friend_first_name, friends.created_at as created_at, friends.updated_at as updated_at  FROM friends join users on friends.friend_id = users.id  where user_id = %s ", (g.loggedin_user_id))    
    friends = g.cur.fetchall()
    if friends is not None :   
        for friend in friends :
            if friend['status'] == 1 :
                g.cur.execute("SELECT lat,lon from users where id = %s",friend['friend_id'])
                result = g.cur.fetchone()
                friend['location'] = result             
        
        return success(friends)
    else :
        return _error("You don't have any friends")


@app.route('/api/v1/user/friend_location', methods=['GET'])
@requires_auth
def get_friend_location():    
    friend_id = request.args['friend_id']
    g.cur.execute("SELECT user_location.lat, user_location.lon, user_location.radius, user_location.created_at, friends.friend_id, friends.user_id, friends.status from friends join user_location on friends.friend_id = user_location.user_id where user_location.user_id = %s and friends.friend_id = %s and friends.user_id = %s and friends.status = 1  order by created_at DESC limit 20", (friend_id,friend_id,g.loggedin_user_id))    
    friends = g.cur.fetchall()   
    
    if friends is not None :                    
        return success(friends)
    else :
        return _error("you are not a friend")


@app.route('/api/v1/user/update_friends', methods=['POST'])
@requires_auth
def update_friend_request_status():    
    friend_id = request.form.get('friend_id')
    
    g.cur.execute("UPDATE  friends SET  status = 1 WHERE  user_id = %s and friend_id = %s",(g.loggedin_user_id, friend_id))
    g.cur.execute("UPDATE  friends SET  status = 1 WHERE  user_id = %s and friend_id = %s",(friend_id, g.loggedin_user_id))
    g.db.commit()
                 
    return success()
    

@app.route('/api/v1/user/location', methods=['GET'])
@requires_auth
def get_location():

    g.cur.execute("select lat, lon, radius, created_at from user_location where user_id = %s order by created_at DESC limit 20", (g.loggedin_user_id,))
    locations = g.cur.fetchall()

    return success(locations)


@app.route('/api/v1/auth', methods=['POST'])
def auth():

    access_token = request.form.get('access_token')    
    data = urllib.urlopen("https://www.googleapis.com/oauth2/v3/tokeninfo?id_token=" + access_token).read()    
    json_response = json.loads(data)
    if  not ('error_description' in json_response ):
             
        g.cur.execute("SELECT * FROM users where email = %s", (json_response['email']))        
        user = g.cur.fetchone()
        
        if user is None:
            g.cur.execute("insert into users (email, lat, lon, first_name, last_name) values (%s, %s, %s, %s, %s)", (json_response['email'], '', '', json_response['given_name'], json_response['family_name'] ))
            g.db.commit()
            user_id = g.cur.lastrowid
            g.cur.execute("SELECT * FROM users where id = %s", (user_id))        
            user = g.cur.fetchone() 
        else:
            user_id = user["id"]
            g.cur.execute("update user_tokens set is_valid = 0 where user_id = %s ", (user_id,))
            g.db.commit()

        token = get_unique_token()

        g.cur.execute("insert into user_tokens (user_id, token) values (%s, %s)", (user_id, token))
        g.db.commit()

        return success({
            "id": user_id,
            "first_name" :  json_response['given_name'],
            "last_name" :  json_response['family_name'] ,
            "lat" : user['lat'],
            "lon" : user['lon'],
            "token": token
        })
    else:        
        return _error(json_response['error_description'])

def get_unique_token():
    token = False
    while 1:
        token = uuid.uuid4().hex
        g.cur.execute("select id from user_tokens where token = %s", (token,))
        found_token = g.cur.fetchone()
        if found_token is None:
            break
    return token


if __name__ == "__main__":
    app.debug = True
    app.logger.setLevel(logging.DEBUG)
    # ASYNC_POOL = Pool(processes=4)
    app.run(debug=True, port=7000, use_reloader=False)
