#!/usr/bin/env python3
"""Builds the better-sidechats demo inside the sandbox OpenCode (see env.sh), then snapshots it so every recording
starts from the same state. Never touches the real install."""
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

B = Path(os.environ.get("BSC_DEMO", "/tmp/bsc-demo"))
PROJECT = str(B / "acme-web")
ENV = {
    **{k: v for k, v in os.environ.items() if k != "OPENCODE_CLI_CONFIG_CONTENT"},
    "PATH": f"{B / 'bin'}:{os.environ['PATH']}",
    "XDG_CONFIG_HOME": str(B / "home/config"),
    "XDG_DATA_HOME": str(B / "home/data"),
    "XDG_STATE_HOME": str(B / "home/state"),
    "XDG_CACHE_HOME": str(B / "home/cache"),
}
DB = B / "home/data/opencode/opencode.db"
MINUTE = 60 * 1000
HOUR = 60 * MINUTE
DAY = 24 * HOUR

MAIN = "Migrate checkout to the new payments SDK"

# Typed text -> what the mock model does. Matched as a substring of the last message the user typed.
SCENARIOS = {
    "Migrate checkout to the new payments SDK": {
        "title": MAIN,
        "reply": "Here's the plan:\n\n1. Replace `LegacyPayments` in `src/payments/client.ts` with the new SDK's client.\n"
        "2. Move `charge()` to `payments.intents.create`, which takes integer cents.\n"
        "3. Rename the webhook events the handler switches on.\n"
        "4. Keep the old client behind a `PAYMENTS_V2` flag until the e2e suite passes.\n\n"
        "Shall I start with the payment client?",
    },
    "start with the payment client": {
        "kind": "read-slow",
        "path": "src/payments/client.ts",
        "reply": "The legacy client divides by 100 before charging (`amountCents / 100`). The new SDK takes cents, so that "
        "division goes away. Replacing the client now.",
    },
    "Which events does the old SDK's webhook send": {
        "title": "Which events does the old SDK's webhook send?",
        "reply": "Three: `charge.succeeded`, `charge.failed` and `refund.created`. The new SDK calls them "
        "`payment_intent.succeeded`, `payment_intent.payment_failed` and `charge.refunded`, so the handler's switch "
        "needs new cases.",
    },
    "Why does the cart store prices in cents": {
        "title": "Why does the cart store prices in cents?",
        "reply": "Because floating point can't represent most decimal amounts exactly: `0.1 + 0.2` is "
        "`0.30000000000000004`. `cartTotal` in `src/checkout/cart.ts` sums integer cents, so totals are exact and only "
        "the UI formats them as dollars. The legacy client is the odd one out: it divides by 100 before charging.",
    },
    "where do we verify webhook signatures": {
        "reply": "In `src/payments/webhooks.ts`. `verifySignature` splits the header into a timestamp and a signature, "
        "recomputes an HMAC-SHA256 of `timestamp.payload` with the webhook secret, and compares the two with "
        "`timingSafeEqual`.",
    },
    "does that stop replayed events": {
        "reply": "Only partly. Events older than five minutes fail (`TOLERANCE_SECONDS = 300`), but nothing records "
        "event IDs, so the same event replayed within those five minutes is accepted. Storing processed event IDs "
        "would close that gap.",
    },
    "add a comment": {
        "kind": "edit",
        "edit": {
            "path": "src/checkout/cart.ts",
            "oldString": "export function cartTotal",
            "newString": "// Amounts are integer cents: summing floats drifts (0.1 + 0.2 !== 0.3).\nexport function cartTotal",
        },
        "reply": "Added a comment above `cartTotal`.",
    },
    "Keep amounts in cents": {
        "reply": "Will do. As the sidechat found, the cart already works in integer cents and the new SDK takes the "
        "amount in the smallest currency unit, so I'll pass `cartTotal()` straight through and drop the `/ 100` the "
        "legacy client needed.",
    },
    "Add dark mode to the settings page": {"title": "Add dark mode to the settings page", "reply": "Done. The settings page follows the system theme and has a toggle."},
    "Update the README install steps": {"title": "Update the README install steps", "reply": "Done. The README uses pnpm and lists the Node version."},
    "Fix the flaky login test in CI": {"title": "Fix the flaky login test in CI", "reply": "Fixed: the test waited for a fixed 500 ms instead of the redirect."},
}

OTHERS = [
    dict(title="Add dark mode to the settings page", age=2 * HOUR + 10 * MINUTE),
    dict(title="Update the README install steps", age=1 * DAY + 3 * HOUR),
    dict(title="Fix the flaky login test in CI", age=2 * DAY + 5 * HOUR),
]
SIDECHATS = [
    dict(question="Which events does the old SDK's webhook send?", age=3 * HOUR),
    dict(question="Why does the cart store prices in cents?", age=25 * MINUTE),
]


def api(method, path, data=None):
    command = ["opencode", "api", method, path]
    if data is not None:
        command += ["--data", json.dumps(data)]
    out = subprocess.run(command, env=ENV, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise SystemExit(f"api {method} {path} failed: {out.stderr or out.stdout}")
    return json.loads(out.stdout).get("data") if out.stdout.strip() else None


def wait_idle(ids, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        active = api("get", "/api/session/active") or {}
        if not any(i in active for i in ids):
            return
        time.sleep(1)
    raise SystemExit(f"sessions still busy: {ids}")


def create(title, text):
    # The agent and model the TUI picks, so it doesn't add "Switched agent/model" lines on the first message.
    session = api(
        "post",
        "/api/session",
        {
            "location": {"directory": PROJECT},
            "title": title,
            "agent": "build",
            "model": {"id": "demo", "providerID": "mock"},
        },
    )
    api("post", f"/api/session/{session['id']}/prompt", {"text": text})
    return session["id"]


def instructions(parent_title):
    # Same note the plugin stores on a sidechat (src/meta.ts, sidechatInstructions).
    return " ".join(
        [
            f'This session is a sidechat of "{parent_title}": a side conversation the user opened to ask about that '
            "session or try something without adding to it.",
            "Answer the user's messages here, and don't carry on that session's task unless they ask.",
            "Every file edit in a sidechat needs the user's approval.",
        ]
    )


def sidechat(parent_id, question):
    """What the plugin does for /btw <question>: fork, mark, archive, then ask."""
    fork = api("post", f"/api/session/{parent_id}/fork", {})
    base = api("get", f"/api/session/{fork['id']}/message?limit=1&order=desc")[0]["id"]
    marker = {"parentID": parent_id, "sessionID": fork["id"], "from": parent_id, "base": base, "created": int(time.time() * 1000)}
    api("patch", f"/api/session/{fork['id']}", {"title": question, "metadata": {"sidechat": marker}, "archived": True})
    api("put", f"/api/experimental/session/{fork['id']}/instructions/entries/sidechat", {"value": instructions(MAIN)})
    api("post", f"/api/session/{fork['id']}/prompt", {"text": question})
    return fork["id"]


def stop():
    subprocess.run(["opencode", "service", "stop"], env=ENV, capture_output=True, timeout=60)
    time.sleep(2)


def backdate(items):
    stop()
    now = int(time.time() * 1000)
    db = sqlite3.connect(DB)
    tables = {row[0] for row in db.execute("select name from sqlite_master where type = 'table'")}
    session_table = "session_v2" if "session_v2" in tables else "session"
    for item in items:
        row = db.execute(f"select time_updated from {session_table} where id = ?", (item["id"],)).fetchone()
        delta = row[0] - (now - int(item["age"]))
        for column in ("time_created", "time_updated", "time_busy", "time_idle", "time_viewed"):
            try:
                db.execute(f"update {session_table} set {column} = {column} - ? where id = ? and {column} is not null", (delta, item["id"]))
            except sqlite3.OperationalError:
                pass
        for table in ("session_message", "session_part"):
            if table in tables:
                db.execute(f"update {table} set time_created = time_created - ?, time_updated = time_updated - ? where session_id = ?", (delta, delta, item["id"]))
    db.commit()
    db.close()


def snapshot():
    stop()
    target = B / "snapshot"
    shutil.rmtree(target, ignore_errors=True)
    for name in ("data", "state"):
        shutil.copytree(B / "home" / name, target / name, symlinks=True)


def main():
    (B / "mock/scenarios.json").write_text(json.dumps(SCENARIOS, indent=1))
    for item in OTHERS:
        item["id"] = create(item["title"], item["title"] + ".")
    main_id = create(MAIN, MAIN + ".")
    wait_idle([item["id"] for item in OTHERS] + [main_id])
    for item in SIDECHATS:
        item["id"] = sidechat(main_id, item["question"])
        wait_idle([item["id"]])
    backdate(OTHERS + SIDECHATS)
    snapshot()
    plan = {"main": main_id, "others": OTHERS, "sidechats": SIDECHATS}
    (B / "plan.json").write_text(json.dumps(plan, indent=1))
    print(json.dumps(plan, indent=1))


if __name__ == "__main__":
    main()
