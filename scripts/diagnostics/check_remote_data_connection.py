import subprocess
import psycopg2
from psycopg2.extras import RealDictCursor

# Remote DB connection parameters
DB_HOST = "167.233.246.102"
DB_PORT = 5432
DB_NAME = "leadhunter_db"
DB_USER = "postgres"
DB_PASS = "leadhunter_pass"

# Fallback SSH command runner
def run_ssh_query(sql):
    cmd = [
        "ssh", "-i", r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem",
        "-o", "StrictHostKeyChecking=no",
        "root@167.233.246.102",
        f"""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "{sql}" """
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout, res.stderr

def main():
    print("Testing direct connection to remote PostgreSQL...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            connect_timeout=5
        )
        print("Connected directly to PostgreSQL!")
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT count(*) as total_leads FROM leads;")
        print("Leads count:", cur.fetchone())
        
        cur.execute("SELECT count(*) as total_posts FROM channel_posts;")
        print("Posts count:", cur.fetchone())
        
        conn.close()
    except Exception as e:
        print("Direct connect error:", e)
        print("Trying via SSH docker command...")
        out, err = run_ssh_query("SELECT count(*) FROM leads; SELECT count(*) FROM channel_posts;")
        print("Output:\n", out)
        if err:
            print("Error:\n", err)

if __name__ == "__main__":
    main()
