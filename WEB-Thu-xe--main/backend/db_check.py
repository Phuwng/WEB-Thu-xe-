import sqlite3
import os
basedir = os.path.abspath(os.path.dirname(__file__))
path = os.path.join(basedir, 'data.db')
print('db', path, 'exists', os.path.exists(path))
if os.path.exists(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    print('vehicles', cur.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0])
    print('users', cur.execute('SELECT COUNT(*) FROM users').fetchone()[0])
    print('orders', cur.execute('SELECT COUNT(*) FROM orders').fetchone()[0])
    print('appointments', cur.execute('SELECT COUNT(*) FROM appointments').fetchone()[0])
    print('sample vehicles:')
    for row in cur.execute('SELECT id, name, status, is_approved FROM vehicles LIMIT 5'):
        print(dict(row))
    conn.close()