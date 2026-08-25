import os
import sys
import sqlite3
import re
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL credentials
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_pg_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def clean_telegram_link(link: str):
    """
    Cleans a Telegram link and extracts the username or private invite link.
    Returns (type, identifier)
    type: 'public' (username) or 'private' (raw invite link)
    """
    if not link:
        return None, None
    link = link.strip()
    
    # Private link detection (+ or joinchat)
    if '/joinchat/' in link or '/+' in link or 't.me/+' in link:
        return 'private', link
        
    # Public link: extract username
    match = re.search(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})', link, re.IGNORECASE)
    if match:
        return 'public', match.group(1)
        
    # Username format without link
    if link.startswith('@'):
        return 'public', link.lstrip('@')
        
    if re.match(r'^[a-zA-Z0-9_]{5,32}$', link):
        return 'public', link
        
    return None, None

def clean_contact_username(username: str):
    """Strips any leading @ and spaces from contact usernames"""
    if not username:
        return None
    username = username.strip().lstrip('@')
    if re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
        return username
    return None

def main():
    sqlite_db_path = "telegram_bot.db"
    
    if not os.path.exists(sqlite_db_path):
        print(f"Error: SQLite database '{sqlite_db_path}' not found in the current working directory.")
        sys.exit(1)
        
    print(f"Connecting to old SQLite database: {sqlite_db_path}...")
    try:
        sqlite_conn = sqlite3.connect(sqlite_db_path)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cur = sqlite_conn.cursor()
    except Exception as e:
        print(f"Error connecting to SQLite: {e}")
        sys.exit(1)
        
    print("Connecting to target PostgreSQL database...")
    try:
        pg_conn = get_pg_connection()
        pg_cur = pg_conn.cursor()
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sqlite_conn.close()
        sys.exit(1)
        
    print("Reading channels table from SQLite...")
    try:
        sqlite_cur.execute("SELECT * FROM channels")
        channels = sqlite_cur.fetchall()
        print(f"Found {len(channels)} channel rows in SQLite database.")
    except Exception as e:
        print(f"Error reading channels from SQLite: {e}")
        sqlite_conn.close()
        pg_conn.close()
        sys.exit(1)

    leads_inserted = 0
    leads_updated = 0
    seeds_inserted = 0
    skipped_rows = 0

    for i, row in enumerate(channels):
        raw_link = row['link']
        name = row['name']
        subscribers = row['subscribers_count']
        owner = row['owner_username']
        old_status = row['status']
        created_at = row['created_at']
        category = row['category'] or 'unknown'

        link_type, identifier = clean_telegram_link(raw_link)
        
        if not link_type or not identifier:
            print(f"Row {i+1}: Cannot parse link '{raw_link}' (Name: {name}). Skipping.")
            skipped_rows += 1
            continue

        # Map Status
        new_status = 'new'
        if old_status in ('sent', 'contacted'):
            new_status = 'contacted'
        elif old_status == 'rejected':
            new_status = 'rejected'

        if link_type == 'private':
            # Private invite link: insert to seed_channels
            try:
                pg_cur.execute(
                    "INSERT INTO seed_channels (channel_username, processed) VALUES (%s, FALSE) ON CONFLICT DO NOTHING",
                    (identifier,)
                )
                seeds_inserted += 1
            except Exception as e:
                print(f"Row {i+1}: Failed inserting seed '{identifier}': {e}")
                pg_conn.rollback()
                skipped_rows += 1
        
        elif link_type == 'public':
            # Public username channel: insert/update leads
            cleaned_owner = clean_contact_username(owner)
            
            # Category and intent calculations
            forex_category = category if category else 'unknown'
            forex_intent = 80 if category.lower() == 'forex' else 10
            lead_score = 75 if forex_intent == 80 else 10

            try:
                pg_cur.execute("""
                    INSERT INTO leads (
                        channel_username, member_count, contact_username, status,
                        forex_category, forex_intent_score, lead_score, tier, is_group, last_activity
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, 'Tier_D', FALSE, %s
                    ) ON CONFLICT (channel_username) DO UPDATE SET
                        member_count = EXCLUDED.member_count,
                        contact_username = COALESCE(NULLIF(leads.contact_username, ''), EXCLUDED.contact_username),
                        last_activity = EXCLUDED.last_activity
                    RETURNING (xmax = 0) AS inserted
                """, (
                    identifier, subscribers, cleaned_owner, new_status,
                    forex_category, forex_intent, lead_score, created_at
                ))
                
                # Check returning if inserted vs updated
                result = pg_cur.fetchone()
                if result and result[0]:
                    leads_inserted += 1
                else:
                    leads_updated += 1
                    
            except Exception as e:
                print(f"Row {i+1}: Failed inserting lead '{identifier}': {e}")
                pg_conn.rollback()
                skipped_rows += 1

        # Commit batch every 50 records to be safe
        if (i + 1) % 50 == 0:
            pg_conn.commit()

    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()

    print("\n" + "="*40)
    print("MIGRATION SUMMARY:")
    print(f"  Total Rows Examined:   {len(channels)}")
    print(f"  Leads Inserted (New):  {leads_inserted}")
    print(f"  Leads Updated (Exist): {leads_updated}")
    print(f"  Seeds Inserted (Priv): {seeds_inserted}")
    print(f"  Rows Skipped/Errors:   {skipped_rows}")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
