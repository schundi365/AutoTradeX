"""Check bot status and logs"""
import duckdb
from pathlib import Path

# Check system logs
db_path = Path("data/system_logs.duckdb")
if db_path.exists():
    con = duckdb.connect(str(db_path), read_only=True)
    count = con.execute("SELECT COUNT(*) FROM system_logs").fetchone()[0]
    print(f"Total logs in database: {count}")
    
    if count > 0:
        print("\nLatest 10 logs:")
        for row in con.execute("SELECT timestamp, level, agent, message FROM system_logs ORDER BY timestamp DESC LIMIT 10").fetchall():
            print(f"{row[0]} | {row[1]:8} | {row[2]:20} | {row[3][:100]}")
    else:
        print("No logs found in database!")
    con.close()
else:
    print(f"Database not found: {db_path}")

# Check if bot is running
print("\n" + "="*80)
print("Checking if trading bot is running...")
import socket
def check_port(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    return result == 0

if check_port(8000):
    print("✓ Trading bot (port 8000): RUNNING")
else:
    print("✗ Trading bot (port 8000): NOT RUNNING")
    
if check_port(8001):
    print("✓ Dashboard backend (port 8001): RUNNING")
else:
    print("✗ Dashboard backend (port 8001): NOT RUNNING")

print("\n" + "="*80)
print("DIAGNOSIS:")
if not check_port(8000):
    print("The trading bot is NOT running!")
    print("This is why you see no logs or activity.")
    print("\nTo start the trading bot:")
    print("  .\\start-trading-bot.ps1")
    print("\nOr manually:")
    print("  python main.py --mode full --autostart")
