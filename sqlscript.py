import os
import sqlite3

# adjust the path to wherever your DB lives
db_path = os.path.expanduser("~/.musicians_organizer.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# show columns in `files` table
cur.execute("PRAGMA table_info(files);")
for col in cur.fetchall():
    # col is a tuple like (cid, name, type, notnull, dflt_value, pk)
    print(col)

conn.close()
