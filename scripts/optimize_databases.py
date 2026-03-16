"""
Optimize dashboard databases by adding indexes and analyzing tables.
"""
import duckdb
from pathlib import Path

def optimize_system_logs():
    """Add indexes to system logs database"""
    db_path = Path("data/system_logs.duckdb")
    
    if not db_path.exists():
        print("System logs database not found")
        return
    
    print("Optimizing system_logs.duckdb...")
    con = duckdb.connect(str(db_path))
    
    try:
        # Add indexes for faster queries
        con.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs(level)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_logs_agent ON system_logs(agent)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_logs_message ON system_logs(message)")
        
        # Analyze table for query optimization
        con.execute("ANALYZE system_logs")
        
        print("✓ System logs optimized")
        print(f"  - Added timestamp index (DESC)")
        print(f"  - Added level index")
        print(f"  - Added agent index")
        print(f"  - Added message index")
        print(f"  - Analyzed table statistics")
        
    except Exception as e:
        print(f"Error optimizing system logs: {e}")
    finally:
        con.close()


def optimize_trade_journal():
    """Add indexes to trade journal database"""
    db_path = Path("data/trading_data.duckdb")
    
    if not db_path.exists():
        print("Trade journal database not found")
        return
    
    print("\nOptimizing trading_data.duckdb...")
    con = duckdb.connect(str(db_path))
    
    try:
        # Check if decisions table exists
        tables = con.execute("SHOW TABLES").fetchall()
        if not any('decisions' in str(t) for t in tables):
            print("  - No decisions table found (empty database)")
            con.close()
            return
        
        # Add indexes for faster queries
        con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_type ON decisions(decision_type)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_entry_id ON decisions(entry_id)")
        
        # Analyze table
        con.execute("ANALYZE decisions")
        
        # Get row count
        count = con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        
        print("✓ Trade journal optimized")
        print(f"  - Added timestamp index (DESC)")
        print(f"  - Added symbol index")
        print(f"  - Added decision_type index")
        print(f"  - Added entry_id index")
        print(f"  - Analyzed table statistics")
        print(f"  - Total decisions: {count:,}")
        
    except Exception as e:
        print(f"Error optimizing trade journal: {e}")
    finally:
        con.close()


def optimize_warehouse():
    """Add indexes to historical data warehouse"""
    db_path = Path("data/historical_data.duckdb")
    
    if not db_path.exists():
        print("\nHistorical data warehouse not found")
        return
    
    print("\nOptimizing historical_data.duckdb...")
    con = duckdb.connect(str(db_path))
    
    try:
        # Check tables
        tables = con.execute("SHOW TABLES").fetchall()
        
        if any('ohlcv' in str(t).lower() for t in tables):
            con.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time ON ohlcv_data(symbol, timestamp DESC)")
            con.execute("ANALYZE ohlcv_data")
            print("✓ OHLCV data optimized")
        else:
            print("  - No OHLCV table found")
        
    except Exception as e:
        print(f"Error optimizing warehouse: {e}")
    finally:
        con.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Database Optimization Script")
    print("=" * 60)
    print()
    
    optimize_system_logs()
    optimize_trade_journal()
    optimize_warehouse()
    
    print()
    print("=" * 60)
    print("Optimization complete!")
    print("=" * 60)
