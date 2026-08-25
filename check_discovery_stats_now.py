import asyncio
import os
import sys
import psycopg2

def main():
    conn = psycopg2.connect(
        dbname="channels_db",
        user="postgres",
        password="mysecretpassword",
        host="167.233.246.102",
        port=5432
    )
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM leads;")
    total_leads = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) FROM leads GROUP BY status;")
    status_counts = dict(cursor.fetchall())

    cursor.execute("SELECT COUNT(*) FROM leads WHERE is_group = True;")
    total_groups = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM leads WHERE is_group = False OR is_group IS NULL;")
    total_channels = cursor.fetchone()[0]

    print(f"📊 LIVE SYSTEM DISCOVERY METRICS:")
    print(f"   Total Discovered Entities in Database: {total_leads}")
    print(f"   Breakdown by Status: {status_counts}")
    print(f"   Total Discovered Channels: {total_channels}")
    print(f"   Total Discovered Groups: {total_groups}")

    conn.close()

if __name__ == "__main__":
    main()
