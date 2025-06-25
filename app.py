import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
socketio = SocketIO(app, async_mode='eventlet')
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(20))
    recipient = db.Column(db.String(20), default="public")
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    return render_template('chat.html', username=current_user.username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect('/')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_user = User(username=request.form['username'], password=request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/login')

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])
    emit("status", f"{data['username']} joined {data['room']}", room=data['room'])

@socketio.on('message')
@login_required
def handle_message(data):
    msg = Message(sender=current_user.username, recipient=data.get('room', 'public'), content=data['msg'])
    db.session.add(msg)
    db.session.commit()
    timestamp = datetime.utcnow().strftime('%H:%M')
    emit("message", f"[{timestamp}] {current_user.username}: {data['msg']}", room=data['room'])

@socketio.on('private_message')
def private_message(data):
    emit("private", f"[PRIVATE] {data['sender']}: {data['msg']}", room=data['recipient'])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=10000, debug=True)