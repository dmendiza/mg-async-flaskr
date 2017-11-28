import os
import sqlite3

import pika
from flask import Flask, flash, g, render_template, request, redirect, url_for
from passlib.hash import pbkdf2_sha256


app = Flask(__name__)
app.config.from_object(__name__)
app.config.update(
    DATABASE=os.path.join(app.root_path, 'flaskr.db'),
    SECRET_KEY='DEVELOPMENT_SECRET_KEY',
    RABBITMQ_HOST='localhost'
)
app.config.from_envvar('FLASKR_SETTINGS', silent=True)


def connect_db():
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def get_db():
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


@app.cli.command('initdb')
def initdb_command():
    init_db()
    print('Initialized the database.')


def connect_queue():
    if not hasattr(g, 'rabbitmq'):
        g.rabbitmq = pika.BlockingConnection(
            pika.ConnectionParameters(app.config['RABBITMQ_HOST'])
        )
    return g.rabbitmq


def get_welcome_queue():
    if not hasattr(g, 'welcome_queue'):
        conn = connect_queue()
        channel = conn.channel()
        channel.queue_declare(queue='welcome_queue', durable=True)
        channel.queue_bind(exchange='amq.direct', queue='welcome_queue')
        g.welcome_queue = channel
    return g.welcome_queue


@app.teardown_appcontext
def close_queue(error):
    if hasattr(g, 'rabbitmq'):
        g.rabbitmq.close()


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if not (email or password):
            return signup_error('Email Address and Password are required.')
        db = get_db()
        c = db.cursor()
        c.execute('SELECT * FROM users WHERE email=?;', (email,))
        if c.fetchone():
            return signup_error('Email Addres already has an account.')
        c.execute('INSERT INTO users (email, password) VALUES (?, ?);',
                  (email, pbkdf2_sha256.hash(password)))
        db.commit()
        q = get_welcome_queue()
        q.basic_publish(
            exchange='amq.direct',
            routing_key='welcome_queue',
            body=email,
            properties=pika.BasicProperties(
                delivery_mode=_DELIVERY_MODE_PERSISTENT
            )
        )
        flash('Account Created')
        return redirect(url_for('login'))
    else:
        return render_template('signup.html')


def send_welcome_email(address):
    res = requests.post(
        "https://api.mailgun.net/v3/{}/messages".format(app.config['DOMAIN']),
        auth=("api", MAILGUN_API_KEY),
        data={"from": "Flaskr <noreply@{}>".format(app.config['DOMAIN']),
              "to": [address],
              "subject": "Welcome to Flaskr!",
              "text": "Welcome to Flaskr, your account is now active!"}
    )
    if res.status_code != 200:
        # Something terrible happened :-O
        raise MailgunError("{}-{}".format(res.status_code, res.reason))


def signup_error(error):
    return render_template('signup.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if not email or password:
            return login_error('Email Address and Password are required.')
        db = get_db()
        with db.cursor() as c:
            c.execute('SELECT * FROM users WHERE email=?;', (email,))
            row = c.fetchone()
            if not row:
                return login_error('Login error.  Check your email address and'
                                   ' password.')
            pass_hash = row[2]
            if not pbkdf2_sha256.verify(password, pass_hash):
                return login_error('Login error.  Check your email address and'
                                   ' password.')
            else:
                session['user'] = email
                return redirect(url_for('index'))
    else:
        return render_template('login.html')


def login_error(error):
    return render_template('login.html', error=error)


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')
