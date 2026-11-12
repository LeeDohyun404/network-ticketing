import sqlite3, glob

file_db = glob.glob("instance/*.db")
print("Database:", file_db)
con = sqlite3.connect(file_db[0])
cur = con.cursor()

cur.execute("DELETE FROM ticket_logs")
cur.execute("DELETE FROM tickets")
cur.execute("DELETE FROM users WHERE role = 'teknisi'")
con.commit()

print("Sisa user:", cur.execute("SELECT id, nama, role FROM users").fetchall())
con.close()