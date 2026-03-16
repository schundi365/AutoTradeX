# APEX Dashboard Startup Guide

This guide provides step-by-step instructions for starting the APEX Trading Dashboard (backend + frontend).

## Architecture Overview

The dashboard consists of two components:

- **Backend (FastAPI)**: Port 8001 - Provides REST API and WebSocket endpoints
- **Frontend (React + Vite)**: Port 3000 - User interface with real-time updates

## Prerequisites

### Backend Requirements
- Python 3.8+
- Virtual environment (recommended)
- Required Python packages installed

### Frontend Requirements
- Node.js 18+
- npm (comes with Node.js)

## First-Time Setup

### 1. Backend Setup

```bash
# Navigate to project root
cd C:\Users\srika\Labs\AgenticAI\AutoTrade

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend/dashboard

# Install Node.js dependencies (first time only)
npm install
```

This will install all required packages including Vite, React, and other dependencies.

## Starting the Dashboard

### Quick Start (Recommended) - Single Command

The easiest way to start both servers with one command:

#### Option 1: PowerShell Script (Recommended)

```powershell
.\start-dashboard.ps1
```

This will:
- ✅ Check if virtual environment exists
- ✅ Check if npm dependencies are installed (installs if missing)
- ✅ Start backend in a new terminal window (port 8001)
- ✅ Start frontend in a new terminal window (port 3000)
- ✅ Automatically open http://localhost:3000 in your browser

**First time setup:** If you get an execution policy error, run this once:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Option 2: Batch File

```cmd
start-dashboard.bat
```

Same functionality as the PowerShell script, but uses Windows batch file.

#### Stopping the Dashboard

To stop both servers:

```powershell
# PowerShell
.\stop-dashboard.ps1

# Or Batch
stop-dashboard.bat

python main.py --mode full --autostart --port 8000
```

Or simply close the backend and frontend terminal windows.

---

### Manual Start (Alternative Method)

If you prefer to start servers manually in separate terminal windows:

### Terminal 1: Start Backend (Port 8001)

```bash
# Navigate to project root
cd C:\Users\srika\Labs\AgenticAI\AutoTrade

# Activate virtual environment
.venv\Scripts\activate

# Start backend server
python -m api.dashboard_backend
```

**Expected output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

**Alternative method (if module approach doesn't work):**
```bash
# Set PYTHONPATH to include current directory
set PYTHONPATH=%CD%

# Run backend
python api/dashboard_backend.py
```

### Terminal 2: Start Frontend (Port 3000)

```bash
# Navigate to frontend directory
cd C:\Users\srika\Labs\AgenticAI\AutoTrade\frontend\dashboard

# Start development server
npm run dev
```

**Expected output:**
```
  VITE v5.0.0  ready in 500 ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
  ➜  press h to show help
```

### 3. Access the Dashboard

Open your browser and navigate to:

```
http://localhost:3000
```

The frontend will automatically proxy API requests to the backend on port 8001.

## Troubleshooting

### Backend Issues

#### Error: `ModuleNotFoundError: No module named 'core'`

**Cause:** Python can't find the project modules because you're not running from the project root.

**Solution:**
```bash
# Make sure you're in the project root
cd C:\Users\srika\Labs\AgenticAI\AutoTrade

# Use the module approach
python -m api.dashboard_backend

# OR set PYTHONPATH
set PYTHONPATH=%CD%
python api/dashboard_backend.py
```

#### Error: `ModuleNotFoundError: No module named 'fastapi'`

**Cause:** Python dependencies not installed.

**Solution:**
```bash
# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Port 8001 Already in Use

**Solution:**
```bash
# Find and kill the process using port 8001
netstat -ano | findstr :8001
taskkill /PID <PID> /F

# Or change the port in api/dashboard_backend.py
```

### Frontend Issues

#### Error: `'vite' is not recognized as an internal or external command`

**Cause:** Node.js dependencies not installed.

**Solution:**
```bash
cd frontend/dashboard
npm install
```

#### Error: `npm: command not found`

**Cause:** Node.js not installed or not in PATH.

**Solution:**
1. Download and install Node.js from https://nodejs.org/
2. Restart your terminal
3. Verify installation: `node --version` and `npm --version`

#### Port 3000 Already in Use

**Solution:**
```bash
# Kill the process using port 3000
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# Or change the port in frontend/dashboard/vite.config.ts
```

#### WebSocket Connection Failed

**Cause:** Backend not running or not accessible.

**Solution:**
1. Ensure backend is running on port 8001
2. Check backend logs for errors
3. Verify backend is accessible: `curl http://localhost:8001/health`

### API Connection Issues

#### Error: `Network Error` or `CORS Error`

**Cause:** Backend not running or CORS misconfigured.

**Solution:**
1. Ensure backend is running: `http://localhost:8001/health`
2. Check Vite proxy configuration in `frontend/dashboard/vite.config.ts`
3. Check backend CORS settings in `api/dashboard_backend.py`

## Automated Startup Scripts

The project includes automated startup scripts that handle everything for you:

### Available Scripts

| Script | Purpose | Platform |
|--------|---------|----------|
| `start-dashboard.ps1` | Start both servers | PowerShell |
| `start-dashboard.bat` | Start both servers | Windows Batch |
| `stop-dashboard.ps1` | Stop both servers | PowerShell |
| `stop-dashboard.bat` | Stop both servers | Windows Batch |

### What the Start Scripts Do

1. **Validation**
   - Checks if Python virtual environment exists
   - Checks if npm dependencies are installed
   - Installs npm dependencies automatically if missing

2. **Backend Startup**
   - Opens new terminal window for backend
   - Activates virtual environment
   - Starts FastAPI server on port 8001
   - Displays API documentation URL

3. **Frontend Startup**
   - Opens new terminal window for frontend
   - Starts Vite dev server on port 3000
   - Displays dashboard URL

4. **Browser Launch**
   - Automatically opens http://localhost:3000
   - Dashboard ready to use!

### What the Stop Scripts Do

- Finds processes running on ports 8001 and 3000
- Gracefully terminates both servers
- Cleans up resources

### Script Locations

All scripts are located in the project root:

```
C:\Users\srika\Labs\AgenticAI\AutoTrade\
├── start-dashboard.ps1      ← PowerShell start script
├── start-dashboard.bat      ← Batch start script
├── stop-dashboard.ps1       ← PowerShell stop script
└── stop-dashboard.bat       ← Batch stop script
```

## Stopping the Dashboard

### Stop Backend
In the backend terminal, press `Ctrl+C`

### Stop Frontend
In the frontend terminal, press `Ctrl+C`

### Force Stop (if terminals are closed)

```bash
# Kill backend (port 8001)
netstat -ano | findstr :8001
taskkill /PID <PID> /F

# Kill frontend (port 3000)
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

## Production Deployment

For production deployment:

### Backend
```bash
# Build and run with production settings
uvicorn api.dashboard_backend:app --host 0.0.0.0 --port 8001 --workers 4
```

### Frontend
```bash
# Build for production
cd frontend/dashboard
npm run build

# Serve the built files
npm run preview

# Or use a production server like nginx
```

## Environment Variables

Create a `.env` file in the project root:

```env
# Backend
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8001
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://user:pass@localhost/apex

# Frontend (optional)
VITE_API_URL=http://localhost:8001
```

## Health Checks

### Backend Health Check
```bash
curl http://localhost:8001/health
```

Expected response:
```json
{"status": "healthy"}
```

### Frontend Health Check
Open browser to `http://localhost:3000` - should see the dashboard UI.

## Logs

### Backend Logs
- Console output in the backend terminal
- Log files (if configured): `logs/dashboard_backend.log`

### Frontend Logs
- Browser console (F12 → Console tab)
- Vite dev server output in the frontend terminal

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review backend logs for errors
3. Check browser console for frontend errors
4. Verify all prerequisites are installed
5. Ensure both backend and frontend are running

## Quick Reference

| Component | Port | URL | Command |
|-----------|------|-----|---------|
| Backend | 8001 | http://localhost:8001 | `python -m api.dashboard_backend` |
| Frontend | 3000 | http://localhost:3000 | `npm run dev` |
| API Docs | 8001 | http://localhost:8001/docs | (Swagger UI) |
| WebSocket | 8001 | ws://localhost:8001/ws/dashboard | (Auto-connected) |

## Next Steps

After starting the dashboard:

1. **Market State Dashboard**: View real-time market conditions
2. **Performance Analytics**: Monitor trading performance
3. **Trade Journal**: Review trading decisions
4. **Model Performance**: Track ML model metrics
5. **System Health**: Monitor system status

Enjoy using the APEX Trading Dashboard!
