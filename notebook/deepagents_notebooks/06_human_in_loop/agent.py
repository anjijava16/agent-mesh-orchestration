# ============================================================
# Example 06: Human-in-the-Loop — Agent Pauses for Approval
# ============================================================
#
# Sometimes you don't want an agent to act autonomously on
# everything. For sensitive actions (sending emails, deleting
# files, making purchases), you want a HUMAN to review and
# approve before the agent proceeds.
#
# Deep Agents support "Human-in-the-Loop" via LangGraph's
# interrupt mechanism:
#
#   1. Agent starts working on a task
#   2. Before a sensitive tool, it PAUSES and asks for approval
#   3. Human reviews the proposed action
#   4. Human types "yes" → agent continues
#      Human types "no"  → agent stops or tries a different approach
#
# Real-world use cases:
#   - Sending emails on behalf of a user
#   - Deleting or modifying important files
#   - Making API calls that cost money
#   - Publishing content to social media
#   - Executing database queries
#
# Run this file:
#   python 06_human_in_loop/agent.py
# ============================================================

import os
from deepagents import create_deep_agent

# ── SIMULATED "DANGEROUS" TOOLS ───────────────────────────────
#
# These tools simulate actions that have real-world consequences.
# In this demo they just print what they WOULD do, but in production
# they'd send actual emails, delete actual files, etc.

def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email to a recipient.

    ⚠️ This is a sensitive action — always ask for human approval first.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Full email body text

    Returns:
        Confirmation that the email was sent.
    """
    # In production: use smtplib, SendGrid, AWS SES, etc.
    print(f"\n   📧 [SENDING EMAIL]")
    print(f"   To:      {to}")
    print(f"   Subject: {subject}")
    print(f"   Body:    {body[:100]}...")
    return f"✅ Email sent to {to} with subject '{subject}'"


def delete_file(filepath: str) -> str:
    """
    Permanently delete a file from the filesystem.

    ⚠️ This is a destructive action — always ask for human approval first.
    Deleted files cannot be recovered.

    Args:
        filepath: The path to the file to delete

    Returns:
        Confirmation that the file was deleted.
    """
    # In production: os.remove(filepath)
    print(f"\n   🗑️  [DELETING FILE]: {filepath}")
    return f"✅ File '{filepath}' has been permanently deleted"


def post_to_social_media(platform: str, message: str) -> str:
    """
    Post a message to a social media platform.

    ⚠️ This is a public action — always ask for human approval first.
    Once posted, the message will be visible to all followers.

    Args:
        platform: The platform to post to (e.g. "Twitter", "LinkedIn")
        message: The message content to post

    Returns:
        Confirmation with the post URL.
    """
    # In production: call Twitter/LinkedIn/etc API
    print(f"\n   📱 [POSTING TO {platform.upper()}]")
    print(f"   Message: {message[:100]}...")
    return f"✅ Posted to {platform}: '{message[:50]}...'"


def search_files(query: str) -> str:
    """
    Search for files matching a query. This is a safe read-only operation.

    Args:
        query: Search term to look for in filenames

    Returns:
        List of matching files.
    """
    # Safe, read-only operation — no approval needed
    mock_files = [
        "report_2024_q4.pdf",
        "report_2024_q3.pdf",
        "presentation_final.pptx",
        "budget_2025.xlsx",
        "notes_meeting_jan.txt",
    ]
    matches = [f for f in mock_files if query.lower() in f.lower()]
    if not matches:
        return f"No files found matching '{query}'"
    return "Found files:\n" + "\n".join(f"  • {f}" for f in matches)


# ── HUMAN APPROVAL WRAPPER ─────────────────────────────────────
#
# This is the core pattern for human-in-the-loop.
# We wrap sensitive tools with an approval gate.
#
# When the agent tries to use a dangerous tool, this wrapper:
#   1. Shows the user what the agent is about to do
#   2. Asks "yes or no?"
#   3. Either allows or blocks the action

class ApprovalGate:
    """
    Wraps tools with a human approval step.

    Usage:
        gate = ApprovalGate(auto_approve=False)
        safe_send_email = gate.wrap(send_email, "send an email")
    """

    def __init__(self, auto_approve: bool = False):
        """
        Args:
            auto_approve: If True, skip asking and always approve.
                         Set to True for testing, False for production.
        """
        self.auto_approve = auto_approve
        self.approval_log = []  # Track all approval decisions

    def wrap(self, tool_fn, action_description: str):
        """
        Wrap a tool function with a human approval gate.

        Args:
            tool_fn: The original tool function to wrap
            action_description: Human-readable description of what this tool does

        Returns:
            A new function with the same signature but an approval step added.
        """
        def wrapped_tool(**kwargs):
            # Build a clear description of exactly what the agent wants to do
            args_str = ", ".join(f"{k}='{v}'" for k, v in kwargs.items())
            action = f"{tool_fn.__name__}({args_str})"

            print(f"\n{'='*50}")
            print(f"⚠️  AGENT WANTS TO: {action_description.upper()}")
            print(f"{'='*50}")
            print(f"Action: {action}")
            print(f"{'─'*50}")

            if self.auto_approve:
                # In test mode, auto-approve everything
                print("   [AUTO-APPROVED for testing]")
                approved = True
            else:
                # Ask the human
                while True:
                    response = input("   Approve this action? (yes/no): ").strip().lower()
                    if response in ("yes", "y"):
                        approved = True
                        break
                    elif response in ("no", "n"):
                        approved = False
                        break
                    else:
                        print("   Please type 'yes' or 'no'")

            # Log the decision
            self.approval_log.append({
                "action": action,
                "approved": approved,
            })

            if approved:
                print(f"   ✅ Approved — executing...")
                # Call the original tool with the provided arguments
                return tool_fn(**kwargs)
            else:
                print(f"   ❌ Rejected — agent will be informed")
                return (
                    f"REJECTED BY HUMAN: The user did not approve '{action_description}'. "
                    f"Do not attempt this action again unless the user explicitly asks."
                )

        # Copy the original function's metadata so the agent can read the docstring
        wrapped_tool.__name__ = tool_fn.__name__
        wrapped_tool.__doc__ = tool_fn.__doc__

        return wrapped_tool


# ── SET UP APPROVAL GATE ──────────────────────────────────────
#
# Change auto_approve=True to skip prompts during testing
gate = ApprovalGate(auto_approve=False)

# Wrap only the dangerous tools — safe tools don't need approval
safe_send_email = gate.wrap(send_email, "send an email")
safe_delete_file = gate.wrap(delete_file, "permanently delete a file")
safe_post_social = gate.wrap(post_to_social_media, "post to social media")

# search_files is safe (read-only) so no wrapping needed


# ── CREATE THE AGENT ──────────────────────────────────────────
#
# The agent gets both safe tools (no gate) and wrapped tools (with gate).
# It doesn't know the difference — from its perspective they're all just tools.

agent = create_deep_agent(
    tools=[
        search_files,      # ← safe, no approval needed
        safe_send_email,   # ← wrapped with approval gate
        safe_delete_file,  # ← wrapped with approval gate
        safe_post_social,  # ← wrapped with approval gate
    ],
    system_prompt="""You are a helpful personal assistant with access to:
- File search (safe, no approval needed)
- Email sending (requires human approval)
- File deletion (requires human approval — DESTRUCTIVE)
- Social media posting (requires human approval — PUBLIC)

Important: For any sensitive action, the system will automatically ask 
the user for approval before proceeding. You don't need to ask permission
yourself — just use the tool and the system handles the approval gate.

If an action is rejected, acknowledge the rejection and ask the user 
if they'd like you to try a different approach.
""",
)


# ── HELPER ────────────────────────────────────────────────────

def ask(question: str) -> str:
    """Send a message to the agent and return its response."""
    result = agent.invoke({
        "messages": [{"role": "user", "content": question}]
    })
    return result["messages"][-1].content


# ── DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  Human-in-the-Loop Demo")
    print("=" * 60)
    print("The agent will ask for your approval before sensitive actions.")
    print("Type 'yes' to allow or 'no' to reject each action.\n")

    # ── Demo 1: Safe action (no approval needed)
    print("\n📍 Task 1: Safe file search (no approval)")
    print("-" * 40)
    response1 = ask("Can you search for any report files I have?")
    print(f"\n🤖 Agent: {response1}")

    # ── Demo 2: Sensitive action — email (will ask for approval)
    print("\n\n📍 Task 2: Send an email (requires your approval)")
    print("-" * 40)
    response2 = ask(
        "Please send an email to boss@company.com with subject "
        "'Q4 Report Ready' and tell them the quarterly report is "
        "complete and available for review."
    )
    print(f"\n🤖 Agent: {response2}")

    # ── Demo 3: Multiple actions — some approved, some rejected
    print("\n\n📍 Task 3: Multiple actions (you choose what to allow)")
    print("-" * 40)
    response3 = ask(
        "Post a LinkedIn update saying 'Excited to share our Q4 results!', "
        "then delete the file report_2024_q3.pdf since we no longer need it."
    )
    print(f"\n🤖 Agent: {response3}")

    # ── Summary of all decisions made
    print("\n\n" + "=" * 60)
    print("📋 Approval Log (all decisions this session):")
    print("=" * 60)
    for i, entry in enumerate(gate.approval_log, 1):
        status = "✅ Approved" if entry["approved"] else "❌ Rejected"
        print(f"  {i}. {status}: {entry['action'][:60]}...")

    print("\n✅ Demo complete!")
    print("=" * 60)
