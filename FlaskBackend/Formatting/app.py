import os
import uuid
import sqlite3
import logging
from datetime import datetime, timedelta
import sys
import subprocess
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database configuration
DB_DIR = os.path.join(os.getcwd(), 'database')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'lab_reports.db')
DATABASE_URL = f'sqlite:///{DB_PATH}'

# Log Python path for debugging
logger.info(f"Python Path: {sys.path}")

# Try to install PyJWT if not found
try:
    import jwt
except ImportError:
    logger.error("JWT not found, attempting to install PyJWT...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyJWT==2.10.1"])
        import jwt
        logger.info("Successfully installed PyJWT")
    except Exception as e:
        logger.error(f"Failed to install PyJWT: {str(e)}")
        raise

from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Environment variables
CORS_ORIGIN = os.getenv('CORS_ORIGIN', 'https://lab-formatter.vercel.app')
ENV = os.getenv('FLASK_ENV', 'production')
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key')  # Change in production
PORT = int(os.getenv('PORT', 8080))

# Initialize Flask app
app = Flask(__name__)
app.config['ENV'] = ENV
app.config['DEBUG'] = ENV == 'development'
app.config['JWT_SECRET'] = JWT_SECRET

# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": [CORS_ORIGIN],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Configure Socket.IO
socketio = SocketIO(
    app,
    cors_allowed_origins=[CORS_ORIGIN],
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)

# Google Docs API setup
SCOPES = ['https://www.googleapis.com/auth/documents']
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service_account.json')

# Token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
            
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=["HS256"])
            current_user = data['username']
        except:
            return jsonify({'error': 'Token is invalid'}), 401
            
        return f(*args, **kwargs)
    return decorated

# Database setup
def dict_factory(cursor, row):
    """Convert database row to dictionary with datetime handling"""
    d = {}
    for idx, col in enumerate(cursor.description):
        value = row[idx]
        if isinstance(value, datetime):
            value = value.isoformat()
        d[col[0]] = value
    return d

def get_db():
    """Get database connection with datetime handling"""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = dict_factory
    return conn

def init_db():
    """Initialize the database schema"""
    try:
        logger.info(f"Initializing database at {DB_PATH}")
        conn = get_db()
        c = conn.cursor()
        
        # Enable foreign keys
        c.execute('PRAGMA foreign_keys = ON')

        logger.info("[INIT_DB] Creating users table")
        # Create users table
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
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

        logger.info("[INIT_DB] Creating lab_reports table")
        c.execute('''
        CREATE TABLE IF NOT EXISTS lab_reports (
            id TEXT PRIMARY KEY,
            number TEXT NOT NULL,
            statement TEXT NOT NULL,
            authors TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (username)
        )
        ''')

        logger.info("[INIT_DB] Creating questions table")
        c.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            lab_report_id TEXT NOT NULL,
            number TEXT NOT NULL,
            statement TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lab_report_id) REFERENCES lab_reports (id)
        )
        ''')

        logger.info("[INIT_DB] Creating subtopics table")
        c.execute('''
        CREATE TABLE IF NOT EXISTS subtopics (
            id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL,
            title TEXT NOT NULL,
            procedures TEXT,
            explanation TEXT,
            citations TEXT,
            image_url TEXT,
            figure_description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions (id)
        )
        ''')

        conn.commit()
        logger.info("[INIT_DB] Database initialized successfully")
        
        # Verify admin user
        c.execute('SELECT username, password FROM users WHERE username = ?', ('admin',))
        admin_user = c.fetchone()
        if admin_user:
            logger.info("[INIT_DB] Verified admin user exists")
            logger.info(f"[INIT_DB] Admin username: {admin_user[0]}")
        else:
            logger.error("[INIT_DB] Failed to verify admin user")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"[INIT_DB] Error initializing database: {str(e)}")
        logger.exception("[INIT_DB] Full traceback:")
        raise e

# Initialize database at startup
try:
    init_db()
    logger.info("Database initialized at startup")
except Exception as e:
    logger.error(f"Failed to initialize database at startup: {str(e)}")
    raise e  # Re-raise to fail startup if database can't be initialized

# Add root endpoint for testing
@app.route('/')
def root():
    return jsonify({
        'status': 'ok',
        'message': 'Lab Formatter API is running'
    })

# Authentication routes
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        logger.info("[LOGIN] Received login request")
        logger.info(f"[LOGIN] Request headers: {dict(request.headers)}")
        logger.info(f"[LOGIN] Raw request data: {request.get_data(as_text=True)}")
        
        data = request.get_json()
        logger.info(f"[LOGIN] Parsed request data: {data}")
        
        if not data or 'username' not in data or 'password' not in data:
            logger.error("[LOGIN] Missing username or password")
            return jsonify({'error': 'Missing username or password'}), 400
            
        conn = get_db()
        c = conn.cursor()
        
        logger.info(f"[LOGIN] Looking up user: {data['username']}")
        c.execute('SELECT * FROM users WHERE username = ?', (data['username'],))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], data['password']):
            logger.info(f"[LOGIN] Successfully authenticated user: {data['username']}")
            token = jwt.encode({
                'username': user['username'],
                'exp': datetime.utcnow() + timedelta(days=1)
            }, app.config['JWT_SECRET'], algorithm="HS256")
            
            return jsonify({
                'token': token,
                'username': user['username']
            }), 200
        
        logger.error(f"[LOGIN] Invalid credentials for user: {data['username']}")
        return jsonify({'error': 'Invalid username or password'}), 401
        
    except Exception as e:
        logger.error(f"[LOGIN] Unexpected error: {str(e)}")
        logger.exception("[LOGIN] Full traceback:")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/profile', methods=['GET'])
@token_required
def get_profile():
    try:
        token = request.headers['Authorization'].replace('Bearer ', '')
        data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=["HS256"])
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT username, created_at FROM users WHERE username = ?', (data['username'],))
        user = c.fetchone()
        conn.close()
        
        if user:
            return jsonify({
                'username': user['username'],
                'created_at': user['created_at']
            }), 200
            
        return jsonify({'error': 'User not found'}), 404
        
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports', methods=['POST'])
@token_required
def create_lab_report():
    conn = None
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        if 'number' not in data or 'statement' not in data or 'authors' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
            
        report_id = str(uuid.uuid4())
        
        conn = get_db()
        c = conn.cursor()
        
        # Create the table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS lab_reports (
                id TEXT PRIMARY KEY,
                number TEXT NOT NULL,
                statement TEXT NOT NULL,
                authors TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (username)
            )
        ''')
        
        token = request.headers['Authorization'].replace('Bearer ', '')
        data_token = jwt.decode(token, app.config['JWT_SECRET'], algorithms=["HS256"])
        current_user = data_token['username']
        
        c.execute(
            'INSERT INTO lab_reports (id, number, statement, authors, created_by) VALUES (?, ?, ?, ?, ?)',
            (report_id, data['number'], data['statement'], data['authors'], current_user)
        )
        conn.commit()
        
        # Get the created report
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        row = c.fetchone()
        if row:
            report = dict(row)
            report['questions'] = []
            conn.close()
            return jsonify(report), 201
        else:
            conn.close()
            return jsonify({'error': 'Failed to create report'}), 500
            
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error creating lab report: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>', methods=['GET'])
@token_required
def get_lab_report(report_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Get lab report
        c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        
        if not report:
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
            
        report = dict(report)
        
        # Get questions
        c.execute('SELECT * FROM questions WHERE lab_report_id = ? ORDER BY created_at', (report_id,))
        questions = [dict(q) for q in c.fetchall()]
        
        # Get subtopics for each question
        for q in questions:
            c.execute('SELECT * FROM subtopics WHERE question_id = ? ORDER BY created_at', (q['id'],))
            q['subtopics'] = [dict(s) for s in c.fetchall()]
            
        report['questions'] = questions
        
        conn.close()
        return jsonify(report), 200
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error getting lab report: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>', methods=['PUT'])
@token_required
def update_lab_report(report_id):
    conn = None
    try:
        logger.info(f"[UPDATE LAB] Received request for report {report_id}")
        logger.info(f"[UPDATE LAB] Request headers: {dict(request.headers)}")
        logger.info(f"[UPDATE LAB] Raw request data: {request.get_data(as_text=True)}")
        
        data = request.get_json()
        if not data:
            logger.error("[UPDATE LAB] No data provided in request")
            return jsonify({'error': 'No data provided'}), 400
            
        required_fields = ['number', 'statement', 'authors']
        for field in required_fields:
            if field not in data:
                logger.error(f"[UPDATE LAB] Missing required field: {field}")
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        logger.info(f"[UPDATE LAB] Parsed request data: {data}")
        
        conn = get_db()
        c = conn.cursor()
        
        # Check if report exists
        c.execute('SELECT id FROM lab_reports WHERE id = ?', (report_id,))
        if not c.fetchone():
            logger.error(f"[UPDATE LAB] Lab report {report_id} not found")
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
        
        # Update report
        try:
            c.execute('''
                UPDATE lab_reports 
                SET number = ?, statement = ?, authors = ?
                WHERE id = ?
            ''', (data['number'], data['statement'], data['authors'], report_id))
            
            conn.commit()
            logger.info(f"[UPDATE LAB] Successfully updated lab report {report_id}")
            
            # Get the updated report
            c.execute('SELECT * FROM lab_reports WHERE id = ?', (report_id,))
            report = dict(c.fetchone())
            
            # Get questions
            c.execute('SELECT * FROM questions WHERE lab_report_id = ? ORDER BY created_at', (report_id,))
            questions = [dict(q) for q in c.fetchall()]
            
            # Get subtopics for each question
            for q in questions:
                c.execute('SELECT * FROM subtopics WHERE question_id = ? ORDER BY created_at', (q['id'],))
                q['subtopics'] = [dict(s) for s in c.fetchall()]
                
            report['questions'] = questions
            
            conn.close()
            
            # Emit socket event
            logger.info(f"[UPDATE LAB] Emitting lab_report_updated event for {report_id}")
            socketio.emit('lab_report_updated', report, room=report_id)
            
            logger.info(f"[UPDATE LAB] Returning updated report: {report}")
            return jsonify(report), 200
            
        except sqlite3.Error as e:
            logger.error(f"[UPDATE LAB] Database error while updating: {str(e)}")
            conn.rollback()
            return jsonify({'error': f'Database error: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"[UPDATE LAB] Unexpected error: {str(e)}")
        logger.exception("[UPDATE LAB] Full traceback:")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>', methods=['DELETE'])
@token_required
def delete_lab_report(report_id):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # First check if the report exists
        c.execute('SELECT id FROM lab_reports WHERE id = ?', (report_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
            
        # Delete all subtopics associated with questions in this report
        c.execute('''
            DELETE FROM subtopics 
            WHERE question_id IN (
                SELECT id FROM questions WHERE lab_report_id = ?
            )
        ''', (report_id,))
        
        # Delete all questions associated with this report
        c.execute('DELETE FROM questions WHERE lab_report_id = ?', (report_id,))
        
        # Delete the report itself
        c.execute('DELETE FROM lab_reports WHERE id = ?', (report_id,))
        
        conn.commit()
        conn.close()
        
        # Emit socket event to notify all clients
        socketio.emit('lab_report_deleted', {'report_id': report_id}, room=report_id)
        
        return jsonify({'message': 'Lab report and all associated data deleted successfully'}), 200
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error deleting lab report: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>/questions', methods=['POST'])
@token_required
def add_question(report_id):
    conn = None
    try:
        logger.info(f"[ADD QUESTION] Received request for report {report_id}")
        logger.info(f"[ADD QUESTION] Request headers: {dict(request.headers)}")
        logger.info(f"[ADD QUESTION] Request method: {request.method}")
        logger.info(f"[ADD QUESTION] Raw request data: {request.get_data(as_text=True)}")
        
        data = request.get_json()
        logger.info(f"[ADD QUESTION] Parsed request data: {data}")
        
        if not data:
            logger.error("[ADD QUESTION] No data provided in request")
            return jsonify({'error': 'No data provided'}), 400
            
        if 'number' not in data or 'statement' not in data:
            logger.error("[ADD QUESTION] Missing required fields")
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Check if lab report exists
        c.execute('SELECT id FROM lab_reports WHERE id = ?', (report_id,))
        report = c.fetchone()
        if not report:
            logger.error(f"[ADD QUESTION] Lab report {report_id} not found")
            conn.close()
            return jsonify({'error': 'Lab report not found'}), 404
        
        logger.info(f"[ADD QUESTION] Found lab report {report_id}, creating question")
        
        # Create question
        question_id = str(uuid.uuid4())
        try:
            c.execute('''
                INSERT INTO questions (id, lab_report_id, number, statement)
                VALUES (?, ?, ?, ?)
            ''', (question_id, report_id, data['number'], data['statement']))
            
            conn.commit()
            logger.info(f"[ADD QUESTION] Successfully created question {question_id}")
            
            # Get the created question
            c.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
            question = c.fetchone()
            if question:
                question = dict(question)
                question['subtopics'] = []
                
                # Emit socket event
                logger.info(f"[ADD QUESTION] Emitting question_added event for {question_id} to room {report_id}")
                socketio.emit('question_added', question, room=report_id)
                
                conn.close()
                logger.info(f"[ADD QUESTION] Returning question data: {question}")
                return jsonify(question), 201
            else:
                logger.error(f"[ADD QUESTION] Failed to retrieve created question {question_id}")
                conn.close()
                return jsonify({'error': 'Failed to create question'}), 500
                
        except sqlite3.Error as e:
            logger.error(f"[ADD QUESTION] Database error while creating question: {str(e)}")
            if conn:
                conn.close()
            return jsonify({'error': f'Database error: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"[ADD QUESTION] Unexpected error: {str(e)}")
        logger.exception("[ADD QUESTION] Full traceback:")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>/questions/<question_id>/subtopics', methods=['POST'])
@token_required
def add_subtopic(report_id, question_id):
    conn = None
    try:
        data = request.json
        conn = get_db()
        c = conn.cursor()
        
        # Check if question exists and belongs to the lab report
        c.execute('''
            SELECT q.id 
            FROM questions q
            JOIN lab_reports lr ON lr.id = q.lab_report_id
            WHERE q.id = ? AND lr.id = ?
        ''', (question_id, report_id))
        
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Question not found'}), 404
        
        # Create subtopic
        subtopic_id = str(uuid.uuid4())
        c.execute('''
            INSERT INTO subtopics (
                id, question_id, title, procedures, explanation, citations,
                image_url, figure_description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            subtopic_id, question_id, data['title'],
            data.get('procedures', ''),
            data.get('explanation', ''),
            data.get('citations', ''),
            data.get('image_url', ''),
            data.get('figure_description', '')
        ))
        
        conn.commit()
        
        # Get the created subtopic
        c.execute('SELECT * FROM subtopics WHERE id = ?', (subtopic_id,))
        subtopic = c.fetchone()
        if subtopic:
            subtopic = dict(subtopic)
            
            conn.close()
            
            # Emit socket event
            socketio.emit('subtopic_added', {
                'question_id': question_id,
                'subtopic': subtopic
            }, room=report_id)
            
            return jsonify(subtopic), 201
        else:
            conn.close()
            return jsonify({'error': 'Failed to create subtopic'}), 500
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error adding subtopic: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>/questions/<question_id>/subtopics/<subtopic_id>', methods=['PUT'])
@token_required
def update_subtopic(report_id, question_id, subtopic_id):
    conn = None
    try:
        data = request.json
        conn = get_db()
        c = conn.cursor()
        
        # Check if subtopic exists and belongs to the question and lab report
        c.execute('''
            SELECT s.id 
            FROM subtopics s
            JOIN questions q ON q.id = s.question_id
            JOIN lab_reports lr ON lr.id = q.lab_report_id
            WHERE s.id = ? AND q.id = ? AND lr.id = ?
        ''', (subtopic_id, question_id, report_id))
        
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Subtopic not found'}), 404
        
        # Update subtopic
        c.execute('''
            UPDATE subtopics 
            SET title = ?, procedures = ?, explanation = ?, citations = ?,
                image_url = ?, figure_description = ?
            WHERE id = ?
        ''', (
            data['title'],
            data.get('procedures', ''),
            data.get('explanation', ''),
            data.get('citations', ''),
            data.get('image_url', ''),
            data.get('figure_description', ''),
            subtopic_id
        ))
        
        conn.commit()
        
        # Get the updated subtopic
        c.execute('SELECT * FROM subtopics WHERE id = ?', (subtopic_id,))
        subtopic = c.fetchone()
        if subtopic:
            subtopic = dict(subtopic)
            
            conn.close()
            
            # Emit socket event
            socketio.emit('subtopic_updated', {
                'question_id': question_id,
                'subtopic': subtopic
            }, room=report_id)
            
            return jsonify(subtopic), 200
        else:
            conn.close()
            return jsonify({'error': 'Failed to update subtopic'}), 500
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error updating subtopic: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/lab-reports/<report_id>/questions/<question_id>', methods=['PUT'])
@token_required
def update_question(report_id, question_id):
    conn = None
    try:
        data = request.json
        conn = get_db()
        c = conn.cursor()
        
        # Check if question exists and belongs to the lab report
        c.execute('''
            SELECT q.id 
            FROM questions q
            JOIN lab_reports lr ON lr.id = q.lab_report_id
            WHERE q.id = ? AND lr.id = ?
        ''', (question_id, report_id))
        
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Question not found'}), 404
        
        # Update question
        c.execute('''
            UPDATE questions 
            SET number = ?, statement = ?
            WHERE id = ?
        ''', (data['number'], data['statement'], question_id))
        
        conn.commit()
        
        # Get the updated question with its subtopics
        c.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
        question = c.fetchone()
        if question:
            question = dict(question)
            
            # Get subtopics for this question
            c.execute('SELECT * FROM subtopics WHERE question_id = ?', (question_id,))
            question['subtopics'] = [dict(subtopic) for subtopic in c.fetchall()]
            
            conn.close()
            
            # Emit socket event
            socketio.emit('question_updated', question, room=report_id)
            
            return jsonify(question), 200
        else:
            conn.close()
            return jsonify({'error': 'Failed to update question'}), 500
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error updating question: {str(e)}")
        if conn:
            conn.close()
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
