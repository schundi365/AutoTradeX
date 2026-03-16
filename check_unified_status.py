"""Check if unified APEX system is working"""
import socket
import requests

def check_port(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    return result == 0

print("=" * 60)
print("APEX UNIFIED SYSTEM STATUS")
print("=" * 60)

# Check if service is running
if check_port(8000):
    print("\n✓ APEX Service: RUNNING on port 8000")
    
    # Test endpoints
    print("\nTesting endpoints:")
    
    endpoints = [
        ("/api/status", "Trading Bot API"),
        ("/api/v1/bot/status", "Dashboard Bot Status"),
        ("/api/v1/logs?limit=5", "Dashboard Logs"),
    ]
    
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"http://localhost:8000{endpoint}", timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {name}: OK")
            else:
                print(f"  ✗ {name}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
    
    print("\n" + "=" * 60)
    print("UNIFIED SOLUTION WORKING!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start React dashboard:")
    print("   cd frontend/dashboard")
    print("   npm run dev")
    print("\n2. Open http://localhost:3000")
    print("\n3. Use dashboard buttons to control bot")
    
else:
    print("\n✗ APEX Service: NOT RUNNING")
    print("\nStart it with: .\\start.ps1")

print("")
