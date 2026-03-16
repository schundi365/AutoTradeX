import duckdb
from pathlib import Path

db_path = Path("data/system_logs.duckdb")

if not db_path.exists():
    print("No logs database found")
else:
    con = duckdb.connect(str(db_path), read_only=True)
    
    # Check for trade-related logs
    result = con.execute("""
        SELECT timestamp, level, agent, message 
        FROM system_logs 
        WHERE message LIKE '%TRADE%' 
           OR message LIKE '%position%'
           OR message LIKE '%Opened%'
           OR message LIKE '%Closed%'
        ORDER BY timestamp DESC 
        LIMIT 20
    """).fetchall()
    
    con.close()
    
    if result:
        print(f"Found {len(result)} trade-related logs:\n")
        for row in result:
            print(f"{row[0]} | {row[1]:8} | {row[2]:20} | {row[3]}")
    else:
        print("No trade-related logs found")
