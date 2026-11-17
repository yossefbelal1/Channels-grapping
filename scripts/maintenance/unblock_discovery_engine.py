import psycopg2
import redis
import time

def main():
    conn = psycopg2.connect("host=postgres port=5432 dbname=leadhunter_db user=postgres password=leadhunter_pass")
    r = redis.Redis(host="redis", port=6379, db=0, decode_responses=True)
    
    with conn.cursor() as cur:
        # 1. Delete dead seed dgchll from corpus_channels
        cur.execute("DELETE FROM corpus_channels WHERE channel_username = 'dgchll';")
        print(f"Deleted dgchll from corpus_channels. Rows affected: {cur.rowcount}")
        
        # 2. Insert/Update dgchll as rejected in leads so it is permanently skipped
        cur.execute("""
            INSERT INTO leads (channel_username, status, description, last_graph_scan)
            VALUES ('dgchll', 'rejected', 'Entity does not exist on Telegram', NOW())
            ON CONFLICT (channel_username) DO UPDATE SET 
                status = 'rejected',
                description = 'Entity does not exist on Telegram',
                last_graph_scan = NOW();
        """)
        print(f"Marked dgchll as rejected in leads.")
        conn.commit()
        
    # 3. Clear rate limit cooldowns for helper sessions that are actually healthy
    # acc_14809564829 is healthy (verified live)
    r.delete("health:acc_14809564829:rate_limited_until")
    print("Cleared health:acc_14809564829:rate_limited_until in Redis.")
    
    # Check current cooldown keys
    keys = r.keys("health:*:rate_limited_until*")
    print("Remaining cooldown keys in Redis:", keys)
    for k in keys:
        print(f"  {k} = {r.get(k)}")

    conn.close()

if __name__ == '__main__':
    main()
