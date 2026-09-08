# AgentMesh Documentation Index

## Quick Start Guides

### Getting Started
- **[START_HERE_SERVICES.md](./START_HERE_SERVICES.md)** - 🚀 **START HERE!** Main entry point for services
- **[QUICK_START.md](./QUICK_START.md)** - 2-minute quick reference
- **[START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)** - Comprehensive service startup guide

### Installation
- **[LOCAL_INSTALL.md](./LOCAL_INSTALL.md)** - Local installation guide
- **[FINAL_SETUP_SUCCESS.md](./FINAL_SETUP_SUCCESS.md)** - Setup verification checklist

## Service Documentation

### Main Services
- **[README_SERVICES.md](./README_SERVICES.md)** - Complete service architecture and guide
- **[INFRA_STATUS.md](./INFRA_STATUS.md)** - Docker infrastructure status

### Celery & Background Tasks
- **[CHECK_CELERY.md](./CHECK_CELERY.md)** - How to monitor Celery worker
- **[CELERY_FIXED.md](./CELERY_FIXED.md)** - Celery issues and fixes

### LiteLLM & Backend
- **[BACKEND_LITELLM_FIXED.md](./BACKEND_LITELLM_FIXED.md)** - Backend→LiteLLM connection fix

## Issue Resolution

### Troubleshooting Guides
- **[ISSUES_RESOLVED.md](./ISSUES_RESOLVED.md)** - All resolved issues with solutions
- **[SOLUTION_SUMMARY.md](./SOLUTION_SUMMARY.md)** - Executive summary of fixes
- **[FINAL_STATUS.md](./FINAL_STATUS.md)** - Complete system status report

## Operations

### Logging & Monitoring
- **[LOGGING_GUIDE.md](./LOGGING_GUIDE.md)** - Logging configuration and best practices

## Quick Reference

### Most Important Documents

**For First-Time Users:**
1. Start with: [START_HERE_SERVICES.md](./START_HERE_SERVICES.md)
2. Then read: [QUICK_START.md](./QUICK_START.md)
3. For details: [START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)

**For Troubleshooting:**
1. Check: [ISSUES_RESOLVED.md](./ISSUES_RESOLVED.md)
2. Celery issues: [CHECK_CELERY.md](./CHECK_CELERY.md)
3. Backend issues: [BACKEND_LITELLM_FIXED.md](./BACKEND_LITELLM_FIXED.md)

**For Understanding the System:**
1. Architecture: [README_SERVICES.md](./README_SERVICES.md)
2. Infrastructure: [INFRA_STATUS.md](./INFRA_STATUS.md)
3. Complete status: [FINAL_STATUS.md](./FINAL_STATUS.md)

## Document Categories

### 📚 Guides (How-To)
- START_SERVICES_GUIDE.md
- CHECK_CELERY.md
- LOCAL_INSTALL.md
- LOGGING_GUIDE.md

### 🚀 Quick Start
- START_HERE_SERVICES.md
- QUICK_START.md

### 🏗️ Architecture
- README_SERVICES.md
- INFRA_STATUS.md

### 🔧 Fixes & Solutions
- ISSUES_RESOLVED.md
- CELERY_FIXED.md
- BACKEND_LITELLM_FIXED.md

### 📊 Status Reports
- FINAL_STATUS.md
- SOLUTION_SUMMARY.md
- FINAL_SETUP_SUCCESS.md

## File Organization

```
agentmesh/
├── README.md                    # Main project README
├── docs/                        # All documentation (you are here)
│   ├── INDEX.md                # This file
│   ├── START_HERE_SERVICES.md  # Start here!
│   ├── QUICK_START.md
│   └── ... (all other guides)
├── scripts/                     # Utility scripts
│   ├── run-backend.sh
│   ├── run-frontend.sh
│   └── ... (other utilities)
├── start-services.sh           # Main startup script
├── stop-services.sh            # Main stop script
├── check-services.sh           # Health check script
├── check-celery.sh            # Celery health check
└── start-all-apps.sh          # Start all applications
```

## Getting Help

1. **Can't start services?** → Read [START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)
2. **Celery not working?** → Read [CHECK_CELERY.md](./CHECK_CELERY.md)
3. **Backend can't reach LiteLLM?** → Read [BACKEND_LITELLM_FIXED.md](./BACKEND_LITELLM_FIXED.md)
4. **Want to understand everything?** → Read [ISSUES_RESOLVED.md](./ISSUES_RESOLVED.md)

## Related Files

- **Main README:** [../README.md](../README.md)
- **Scripts Directory:** [../scripts/](../scripts/)
- **Main Startup Script:** [../start-services.sh](../start-services.sh)

---

**Last Updated:** September 8, 2026
