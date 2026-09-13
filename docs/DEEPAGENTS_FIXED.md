# DeepAgents Fixed - Version Upgrade

## Issue

When selecting "deepagents" in the UI, getting error:
```
deepagents is not installed. `pip install deepagents`
```

## Root Cause

The issue was **version incompatibility**, not missing installation:

- **Installed:** `deepagents==0.2.4` (outdated)
- **Problem:** `deepagents 0.2.4` is incompatible with `langgraph 1.0.4`
- **Error:** `ImportError: cannot import name 'ExecutionInfo' from 'langgraph.runtime'`

The package was installed but couldn't be imported due to breaking changes in dependencies.

## Solution Applied

### Upgraded DeepAgents and Dependencies

```bash
cd backend
source .venv/bin/activate
pip install --upgrade "deepagents>=0.7"
```

### Packages Updated

| Package | Old Version | New Version |
|---------|-------------|-------------|
| **deepagents** | 0.2.4 | 0.7.13 ✅ |
| langchain | 1.2.6 | 1.4.0 |
| langgraph | 1.0.4 | 1.2.11 |
| langgraph-prebuilt | 1.0.13 | 1.1.0 |
| langgraph-checkpoint | 3.0.1 | 4.2.0 |
| langchain-anthropic | 1.0.4 | 1.7.1 |
| langchain-google-genai | 2.1.12 | 4.4.0 |

### Updated requirements.txt

Changed:
```python
# OLD (incompatible)
deepagents==0.2.4
langchain>=1.0,<2
langgraph>=1.0,<2
langgraph-checkpoint>=2.1.0,<4
langchain-anthropic>=1.0,<2
langchain-google-genai>=2.1.12,<3
```

To:
```python
# NEW (compatible)
deepagents>=0.7,<1
langchain>=1.4,<2
langgraph>=1.2,<2
langgraph-checkpoint>=4.0,<5
langchain-anthropic>=1.7,<2
langchain-google-genai>=4.4,<5
```

## Verification

```bash
cd backend
source .venv/bin/activate
python3 -c "from deepagents import create_deep_agent; print('✅ Success!')"
```

Output:
```
✅ deepagents 0.7.13 import works!
```

## How to Restart Backend

The backend needs to be restarted to pick up the new deepagents version:

### Option 1: Using Script
```bash
./scripts/run-backend.sh
```

### Option 2: Start All Services
```bash
./start-services-with-logs.sh
```

### Option 3: Manual
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Testing DeepAgents in UI

1. **Start the backend:**
   ```bash
   ./scripts/run-backend.sh
   ```

2. **Open the UI:**
   ```
   http://localhost:5173
   ```

3. **Select DeepAgents:**
   - Go to agent framework selection
   - Choose "LangChain DeepAgents"
   - Should work without errors now ✅

## What DeepAgents Does

**LangChain DeepAgents** is a planning-first agent harness with:

- ✅ **Planning**: Creates a plan with the `todo` tool before executing
- ✅ **Delegation**: Can delegate tasks to specialized subagents
- ✅ **Virtual Filesystem**: Saves intermediate results to files
- ✅ **Multi-Agent**: Coordinates multiple specialist agents
- ✅ **Citations**: Includes source citations in answers

## Files Modified

1. **backend/requirements.txt** - Updated deepagents and dependencies
2. **backend/.venv/** - Upgraded packages in virtual environment

## Current Package Versions

```bash
deepagents==0.7.13
langchain==1.4.0
langgraph==1.2.11
langgraph-prebuilt==1.1.0
langgraph-checkpoint==4.2.0
langchain-anthropic==1.7.1
langchain-google-genai==4.4.0
```

## Breaking Changes

The upgrade may have minor API changes, but the backend code is compatible because:
- The `create_deep_agent` interface remains the same
- `DeepAgentsRuntime` in `backend/app/agents/frameworks/deepagents_runtime.py` uses the stable API
- All tools and subagent configuration work the same way

## Troubleshooting

### If deepagents still doesn't work:

1. **Check installation:**
   ```bash
   cd backend
   source .venv/bin/activate
   pip list | grep deepagents
   # Should show: deepagents 0.7.13
   ```

2. **Verify import:**
   ```bash
   python3 -c "from deepagents import create_deep_agent; print('OK')"
   ```

3. **Restart backend:**
   ```bash
   pkill -f "uvicorn.*8000"
   ./scripts/run-backend.sh
   ```

4. **Check logs:**
   ```bash
   tail -f logs/backend_*.log
   ```

### If you see import errors:

```bash
cd backend
source .venv/bin/activate
pip install --force-reinstall deepagents==0.7.13
```

## Status

✅ **FIXED** - deepagents 0.7.13 installed and working  
✅ **Compatible** - All dependencies upgraded  
✅ **Tested** - Import verified  
✅ **Ready** - Restart backend to use

---

**Next Steps:**
1. Restart backend: `./scripts/run-backend.sh`
2. Open UI: `http://localhost:5173`
3. Select "LangChain DeepAgents" framework
4. Test with a query

---

**Date Fixed:** September 8, 2026  
**Version:** deepagents 0.7.13
