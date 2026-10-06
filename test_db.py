from storage.database import Database
db = Database()
print('Database initialized OK')
tables = db.query("SELECT name FROM sqlite_master WHERE type='table'")
print('Tables:', [t['name'] for t in tables])