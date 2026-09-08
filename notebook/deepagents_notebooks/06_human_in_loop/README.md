# 06 — Human-in-the-Loop: Agent Pauses for Your Approval

> **Difficulty:** ⭐⭐⭐ Intermediate

Autonomous agents are powerful — but for sensitive actions like sending emails, deleting files, or posting publicly, you want a human to **review and approve** before the agent acts. This example shows exactly how to build that safety gate.

---

## 🎯 What You'll Learn

- Why human oversight matters for production agents
- How to build an **approval gate** that wraps any tool
- How to give the agent both **safe tools** (no gate) and **gated tools** (approval required)
- How to **log all decisions** for audit purposes
- Patterns for production human-in-the-loop systems

---

## 📂 Files

```
06_human_in_loop/
├── agent.py      # Agent with approval gate + 4 tools (1 safe, 3 gated)
└── README.md     # This file
```

---

## 🛡️ How the Approval Gate Works

```
Agent decides to call send_email(to="boss@...", subject="...")
                    │
                    ▼
         ┌─────────────────────┐
         │   APPROVAL GATE     │
         │                     │
         │ ⚠️  AGENT WANTS TO: │
         │    SEND AN EMAIL    │
         │                     │
         │ To: boss@company    │
         │ Subject: Q4 Report  │
         │                     │
         │ Approve? (yes/no):  │
         └────────┬────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
       yes                  no
        │                   │
        ▼                   ▼
  Email is sent       Agent is told:
  ✅ Confirmed        "REJECTED BY HUMAN"
                      Agent tries another approach
```

---

## 🔧 Tools in This Example

| Tool | Sensitive? | Gate? | What it does |
|------|-----------|-------|-------------|
| `search_files(query)` | ❌ No | ❌ No gate | Read-only file search |
| `send_email(to, subject, body)` | ✅ Yes | ✅ Gated | Sends emails |
| `delete_file(filepath)` | ✅ Yes | ✅ Gated | Permanently deletes files |
| `post_to_social_media(platform, msg)` | ✅ Yes | ✅ Gated | Posts publicly |

---

## 🔑 Key Code Pattern: The ApprovalGate Class

```python
class ApprovalGate:
    def wrap(self, tool_fn, action_description):
        def wrapped_tool(**kwargs):
            # Show what the agent wants to do
            print(f"⚠️ AGENT WANTS TO: {action_description}")
            print(f"   Action: {tool_fn.__name__}({kwargs})")

            # Ask the human
            response = input("Approve? (yes/no): ").strip().lower()

            if response == "yes":
                return tool_fn(**kwargs)  # Run the real tool
            else:
                return "REJECTED BY HUMAN"  # Tell the agent it was blocked

        # Copy metadata so the agent can read the docstring
        wrapped_tool.__name__ = tool_fn.__name__
        wrapped_tool.__doc__ = tool_fn.__doc__
        return wrapped_tool

# Usage
gate = ApprovalGate()
safe_send_email = gate.wrap(send_email, "send an email")

agent = create_deep_agent(tools=[safe_send_email])
```

The agent doesn't know a gate exists — it just calls the tool. The gate intercepts the call before executing.

---

## ▶️ How to Run

```bash
python 06_human_in_loop/agent.py
```

### Example Session

```
🛡️  Human-in-the-Loop Demo
The agent will ask for your approval before sensitive actions.

📍 Task 2: Send an email (requires your approval)
──────────────────────────────────────────────────

==================================================
⚠️  AGENT WANTS TO: SEND AN EMAIL
==================================================
Action: send_email(to='boss@company.com', subject='Q4 Report Ready', body='...')
──────────────────────────────────────────────────
   Approve this action? (yes/no): yes
   ✅ Approved — executing...

   📧 [SENDING EMAIL]
   To:      boss@company.com
   Subject: Q4 Report Ready
   Body:    The quarterly report is complete...

🤖 Agent: I've sent the email to boss@company.com successfully!
```

---

## 💡 Production Patterns

### Pattern 1: CLI approval (this example)
Simple `input()` calls. Great for scripts and personal automation.

### Pattern 2: Web UI approval
```python
# Store pending approvals in a database
pending_approvals.save({
    "id": approval_id,
    "action": action,
    "status": "pending"
})

# Send notification to human reviewer
notify_reviewer(email, approval_url)

# Agent polls or waits for decision
while True:
    decision = pending_approvals.get(approval_id)
    if decision.status != "pending":
        break
    time.sleep(5)
```

### Pattern 3: Risk-based gating
```python
def smart_gate(tool_fn, risk_level):
    def wrapped(**kwargs):
        if risk_level == "low":
            return tool_fn(**kwargs)  # Auto-approve low risk
        elif risk_level == "medium":
            return ask_human(tool_fn, kwargs)  # Ask for medium
        else:
            return "BLOCKED"  # Never allow high risk
    return wrapped
```

### Pattern 4: Audit logging
```python
# Always log, even for approved actions
audit_log.append({
    "timestamp": datetime.now().isoformat(),
    "tool": tool_fn.__name__,
    "args": kwargs,
    "approved": approved,
    "approver": current_user,
})
```

---

## ➡️ Next Steps

- **[07 — FastAPI Server](../07_fastapi_server/)** — expose your agent as a REST API
