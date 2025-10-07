# create_db.py
import sqlite3

conn = sqlite3.connect('mydatabase.db')
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL
)''')

# Insert sample data (if not exists)
try:
    cursor.execute("INSERT INTO users (id, name, email) VALUES (1, 'Hoang Hong Huy', 'huy.hh@example.com')")
    cursor.execute("INSERT INTO users (id, name, email) VALUES (2, 'Nguyen Van A', 'a.nv@example.com')")
    cursor.execute("INSERT INTO products (id, name, price) VALUES (101, 'Laptop Pro', 1200.50)")
    cursor.execute("INSERT INTO products (id, name, price) VALUES (102, 'AI Mouse', 75.00)")
except sqlite3.IntegrityError:
    print("Data already exists.")

conn.commit()
conn.close()
print("Database 'mydatabase.db' created and populated successfully.")