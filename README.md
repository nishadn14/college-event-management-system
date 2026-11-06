# College Event Management System (Mini Project)

Flask + SQLite web app.

## Features
- Student registration / login (hashed passwords)
- Browse, search and filter events by category
- Register / cancel for events (capacity and past-event checks)
- Admin: dashboard stats, add / edit / delete events, view participants, export CSV

## Run
    python -m venv venv
    venv\Scripts\activate          (Windows)   |   source venv/bin/activate   (Linux/Mac)
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000

Admin login: admin / admin123
The database (events.db) is created automatically on first run with sample events.
