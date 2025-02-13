import os
import sqlite3
import logging
from flask import g

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = os.getenv('DATABASE_FILE')

if not os.path.isfile(DATABASE):
    raise ValueError(f"Database file {DATABASE} not found")

# Used for the flask app
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def get_db_connection():
    conn = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn

# Used by the watcher to write
def execute_query(query, params=(), commit=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    if commit:
        conn.commit()
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result