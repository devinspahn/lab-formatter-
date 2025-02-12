# Lab Report Formatter

A web application for creating and managing lab reports with features like:
- Question and subtopic management
- Image uploads with descriptions
- PDF generation
- Real-time collaboration
- Auto-save functionality

## Project Structure

- `/FlaskBackend` - Python Flask backend
- `/react-frontend` - React.js frontend

## Setup

### Backend
1. Install Python dependencies:
```bash
cd FlaskBackend
pip install -r requirements.txt
```

2. Run the Flask server:
```bash
python Formatting/app.py
```

### Frontend
1. Install Node.js dependencies:
```bash
cd react-frontend
npm install
```

2. Run the React development server:
```bash
npm start
```

## Environment Variables

### Backend
- `PORT` - Server port (default: 8080)
- `DATABASE_URL` - Database connection URL
- `CORS_ORIGIN` - Allowed CORS origin
- `GOOGLE_SERVICE_ACCOUNT_FILE` - Path to Google service account file

### Frontend
- `REACT_APP_BACKEND_URL` - Backend API URL
- `REACT_APP_WS_URL` - WebSocket URL
