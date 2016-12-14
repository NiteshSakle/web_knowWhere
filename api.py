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

app = Flask(__name__)

API_KEY = 'knowWhereAPIKEY'
MYSQL_HOSTNAME = 'localhost'
MYSQL_USERNAME = 'root'
MYSQL_PASSWORD = 'password'
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
    g.cur.execute("SELECT id FROM user_tokens where token = %s and is_valid = 1", (auth,))
    user = g.cur.fetchone()
    if user is not None:
        g.loggegin_user_id = user.id
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

    g.cur.execute("insert into user_locations (user_id, lat, lon, radius) values (%s, %s, %s, %s)", (g.loggegin_user_id, lat, lon, radius))
    g.db.commit()

    return success()


@app.route('/api/v1/user/<user_id>/location', methods=['GET'])
@requires_auth
def get_location(user_id):

    g.cur.execute("select lat, lon, radius, created_at from user_locations where user_id = %s order by created_at DESC limit 20", (g.loggegin_user_id,))
    locations = g.cur.fetchall()

    return success(locations)


@app.route('/api/v1/auth', methods=['POST'])
def auth():

    email = request.form.get('email')
    g.cur.execute("SELECT id FROM users where email = %s", (email,))
    user = g.cur.fetchone()

    if user is None:
        g.cur.execute("insert into users (email) values (%s)", (email,))
        g.db.commit()
        user_id = g.cur.lastrowid
    else:
        user_id = user["id"]
        g.cur.execute("update user_tokens set is_valid = 0 where user_id = %s ", (user_id,))
        g.db.commit()

    token = get_unique_token()

    g.cur.execute("insert into user_tokens (user_id, token) values (%s, %s)", (user_id, token))
    g.db.commit()

    return success({
        user_id: user_id,
        token: token
    })


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
