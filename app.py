import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, g
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXT = {'png','jpg','jpeg','gif','mp3','mp4'}
DB = 'instance/chat.db'

app = Flask(__name__, instance_relative_config=True)
app.config.update(
    SECRET_KEY='dev-key',
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    DATABASE=DB
)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('instance', exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

def get_db():
    db = getattr(g, '_db', None)
    if not db:
        db = g._db = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(e=None):
    db = getattr(g, '_db', None)
    if db: db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, password TEXT);
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, sender_id INTEGER, filename TEXT, text TEXT, timestamp TEXT);
    """)
    db.commit()

@app.route('/', methods=['GET','POST'])
def login():
    if request.method=='POST':
        name = request.form['name']
        pwd = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
        if user and check_password_hash(user['password'], pwd):
            session['user_id'] = user['id']
            session['name'] = user['name']
            return redirect(url_for('chat'))
        else:
            return "Login failed."
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        pwd = request.form['password']
        db = get_db()
        existing = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if existing >= 2:
            return "Only 2 users allowed (for couple use)"
        hashed = generate_password_hash(pwd)
        db.execute("INSERT INTO users(name, password) VALUES (?, ?)", (name, hashed))
        db.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    messages = get_db().execute("SELECT * FROM messages ORDER BY id").fetchall()
    return render_template('chat.html', messages=messages, name=session['name'])

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return '', 403
    file = request.files.get('file')
    text = request.form.get('text', '')
    filename = None
    if file and '.' in file.filename:
        ext = file.filename.rsplit('.',1)[1].lower()
        if ext in ALLOWED_EXT:
            filename = f"{datetime.utcnow().timestamp()}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    ts = datetime.utcnow().isoformat()
    db = get_db()
    db.execute("INSERT INTO messages(sender_id, filename, text, timestamp) VALUES (?, ?, ?, ?)", (session['user_id'], filename, text, ts))
    db.commit()
    emit('new_message', {'sender': session['name'], 'text': text, 'filename': filename, 'timestamp': ts}, room='private_room', namespace='/chat')
    return redirect(url_for('chat'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@socketio.on('join', namespace='/chat')
def on_join():
    join_room('private_room')

if __name__=='__main__':
    init_db()
    socketio.run(app, debug=True)
