import os
import sys
import uuid
import json
import sqlite3
import logging
import subprocess
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Environment variables
CORS_ORIGIN = os.getenv('CORS_ORIGIN', 'https://lab-formatter.vercel.app')
ENV = os.getenv('FLASK_ENV', 'production')
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key')
PORT = int(os.getenv('PORT', 8080))

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# Install required packages if needed
try:
    import jwt
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyJWT"])
        import jwt
    except Exception as e:
        logger.error(f"Failed to install PyJWT: {str(e)}")
        raise

# Database helper functions
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    """Get database connection with datetime handling"""
    conn = sqlite3.connect('lab_reports.db', detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = dict_factory
    return conn

def init_db():
    """Initialize the database schema"""
    try:
        logger.info(f"Initializing database at lab_reports.db")
        conn = get_db()
        c = conn.cursor()
        
        # Create users table
        logger.info("[INIT_DB] Creating users table")
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create admin user if not exists
        logger.info("[INIT_DB] Checking for admin user")
        c.execute('SELECT username FROM users WHERE username = ?', ('admin',))
        admin_exists = c.fetchone()
        
        if not admin_exists:
            logger.info("[INIT_DB] Creating admin user")
            admin_password = generate_password_hash('admin123')
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', admin_password))
            logger.info("[INIT_DB] Admin user created successfully")
        else:
            logger.info("[INIT_DB] Admin user already exists")
        
        # Create lab_reports table
        logger.info("[INIT_DB] Creating lab_reports table")
        c.execute('''
        CREATE TABLE IF NOT EXISTS lab_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL,
            statement TEXT NOT NULL,
            authors TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create questions table
        logger.info("[INIT_DB] Creating questions table")
        c.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_report_id INTEGER,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lab_report_id) REFERENCES lab_reports (id)
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
        
        # Verify admin user
        c.execute('SELECT username FROM users WHERE username = ?', ('admin',))
        admin_user = c.fetchone()
        if admin_user:
            logger.info("[INIT_DB] Verified admin user exists")
            logger.info(f"[INIT_DB] Admin username: {admin_user['username']}")
        else:
            logger.error("[INIT_DB] Failed to verify admin user")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

# Initialize database at startup
init_db()

# Token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Token is missing'}), 401

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401

        return f(*args, **kwargs)
    return decorated

# Lab Report endpoints
@app.route('/api/lab-reports', methods=['GET'])
@token_required
def get_lab_reports():
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM lab_reports ORDER BY updated_at DESC')
        reports = c.fetchall()
        
        # Get questions for each report
        for report in reports:
            c.execute('SELECT * FROM questions WHERE lab_report_id = ?', (report['id'],))
            report['questions'] = c.fetchall()
        
        conn.close()
        return jsonify(reports)
    except Exception as e:
        logger.error(f"Error getting lab reports: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports', methods=['POST'])
@token_required
def create_lab_report():
    try:
        data = request.get_json()
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''
        INSERT INTO lab_reports (number, statement, authors)
        VALUES (?, ?, ?)
        ''', (data['number'], data['statement'], data['authors']))
        
        report_id = c.lastrowid
        
        # Insert questions if provided
        if 'questions' in data:
            for question in data['questions']:
                c.execute('''
                INSERT INTO questions (lab_report_id, content)
                VALUES (?, ?)
                ''', (report_id, question['content']))
        
        conn.commit()
        
        # Get the created report
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        # Get questions
        c.execute('SELECT * FROM questions WHERE lab_report_id = ?', (report_id,))
        report['questions'] = c.fetchall()
        
        conn.close()
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error creating lab report: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<int:report_id>', methods=['GET'])
@token_required
def get_lab_report(report_id):
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        if not report:
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
        
        c.execute('SELECT * FROM questions WHERE lab_report_id = ?', (report_id,))
        report['questions'] = c.fetchall()
        
        conn.close()
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error getting lab report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<int:report_id>', methods=['PUT'])
@token_required
def update_lab_report(report_id):
    try:
        data = request.get_json()
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        if not report:
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
        
        c.execute('''
        UPDATE lab_reports 
        SET number = ?, statement = ?, authors = ?
        WHERE id = ?
        ''', (data['number'], data['statement'], data['authors'], report_id))
        
        conn.commit()
        
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        c.execute('SELECT * FROM questions WHERE lab_report_id = ?', (report_id,))
        report['questions'] = c.fetchall()
        
        conn.close()
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error updating lab report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<int:report_id>', methods=['DELETE'])
@token_required
def delete_lab_report(report_id):
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        if not report:
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
        
        c.execute('DELETE FROM questions WHERE lab_report_id = ?', (report_id,))
        c.execute('DELETE FROM lab_reports WHERE id = ?', (report_id,))
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Lab report deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting lab report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<int:report_id>/questions', methods=['POST'])
@token_required
def add_question(report_id):
    try:
        data = request.get_json()
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        if not report:
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
        
        c.execute('''
        INSERT INTO questions (lab_report_id, content)
        VALUES (?, ?)
        ''', (report_id, data['content']))
        
        question_id = c.lastrowid
        conn.commit()
        
        # Get the created question with all fields
        c.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
        question = c.fetchone()
        
        conn.close()
        return jsonify(question)
    except Exception as e:
        logger.error(f"Error adding question: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<int:report_id>/questions/<int:question_id>', methods=['PUT'])
@token_required
def update_question(report_id, question_id):
    try:
        data = request.get_json()
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
        question = c.fetchone()
        
        if not question:
            conn.close()
            return jsonify({'error': 'Question not found'}), 404
        
        c.execute('''
        UPDATE questions 
        SET content = ?
        WHERE id = ?
        ''', (data['content'], question_id))
        
        conn.commit()
        
        c.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
        question = c.fetchone()
        
        conn.close()
        return jsonify(question)
    except Exception as e:
        logger.error(f"Error updating question: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<int:report_id>/questions/<int:question_id>', methods=['DELETE'])
@token_required
def delete_question(report_id, question_id):
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
        question = c.fetchone()
        
        if not question:
            conn.close()
            return jsonify({'error': 'Question not found'}), 404
        
        c.execute('DELETE FROM questions WHERE id = ?', (question_id,))
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Question deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting question: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Authentication routes
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE username = ?', (data['username'],))
        user = c.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        if not check_password_hash(user['password'], data['password']):
            conn.close()
            return jsonify({'error': 'Invalid password'}), 401
        
        token = jwt.encode({
            'username': user['username'],
            'exp': datetime.utcnow() + timedelta(days=1)
        }, JWT_SECRET, algorithm="HS256")
        
        conn.close()
        return jsonify({'token': token})
    except Exception as e:
        logger.error(f"Error logging in: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/profile', methods=['GET'])
@token_required
def get_profile():
    try:
        token = request.headers['Authorization'].replace('Bearer ', '')
        data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE username = ?', (data['username'],))
        user = c.fetchone()
        
        conn.close()
        return jsonify(user)
    except Exception as e:
        logger.error(f"Error getting profile: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Health check endpoint
@app.route('/api/health')
def health_check():
    return '', 200  # Just return empty 200 OK response

# Socket.IO event handlers
@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        logger.info(f'Client joined room: {room}')
        emit('message', {'msg': f'Joined room: {room}'})

@socketio.on('leave')
def handle_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)
        logger.info(f'Client left room: {room}')
        emit('message', {'msg': f'Left room: {room}'})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    socketio.run(app, 
                host='0.0.0.0',
                port=port,
                debug=ENV == 'development',
                use_reloader=ENV == 'development',
                allow_unsafe_werkzeug=True)  # Allow binding to 0.0.0.0
