#!/usr/bin/env python3
"""Writes the VHS tapes for the better-sidechats demo. Usage: tapes.py  (writes tapes/*.tape)"""
import json
import os
from pathlib import Path

B = Path(os.environ.get("BSC_DEMO", "/tmp/bsc-demo"))
OUT = Path("media")
(B / "tapes").mkdir(exist_ok=True)
(B / OUT).mkdir(exist_ok=True)
plan = json.loads((B / "plan.json").read_text())

HEADER = """Output {out}/{name}.gif
Set Shell "bash"
Set FontFamily "CaskaydiaMono NFM"
Set FontSize 16
Set Width 1200
Set Height 820
Set Padding 20
Set WindowBar Colorful
Set BorderRadius 10
Set Theme "tokyonight"
Set TypingSpeed 55ms
Set CursorBlink false
Hide
Type "source {b}/env.sh && cd {b}/acme-web && python3 {b}/prep.py {prep} && clear && opencode -s {main}"
Enter
Sleep 7s
Show
"""

# Every tape starts in the main session. Its sidechats, newest first: "Why does the cart store prices in cents?",
# "Which events does the old SDK's webhook send?".
TAPES = {
    # /btw while the main session works, a follow-up, back to the main session, the tab.
    "btw": ("btw", """
Sleep 2.5s
Type "/btw where do we verify webhook signatures?"
Sleep 700ms
Enter
Sleep 4s
Screenshot {out}/banner.png
Type "does that stop replayed events?"
Sleep 600ms
Enter
Sleep 4.5s
Ctrl+X
Type "p"
Sleep 2.5s
Down
Sleep 1s
Left
Sleep 3s
Screenshot {out}/tab.png
Sleep 1s
Escape
Sleep 1.5s
"""),
    # Open a sidechat from the tab; inside it the tab lists the main session first.
    "tab": ("default", """
Sleep 1.5s
Down
Sleep 1s
Left
Sleep 2s
Down
Sleep 1s
Enter
Sleep 3s
Down
Sleep 1s
Left
Sleep 3s
Screenshot {out}/tab-sidechat.png
Up
Sleep 700ms
Up
Sleep 1s
Enter
Sleep 3s
"""),
    # Bring back, then the main session uses it with the next message.
    "bring-back": ("default", """
Sleep 1.5s
Down
Sleep 1s
Left
Sleep 2s
Ctrl+B
Sleep 3s
Escape
Sleep 2s
Type "Keep amounts in cents when you call the new SDK"
Sleep 700ms
Enter
Sleep 6s
"""),
    # An edit in a sidechat asks first.
    "edit": ("default", """
Sleep 1.5s
Down
Sleep 1s
Left
Sleep 2s
Enter
Sleep 3s
Type "add a comment there explaining why"
Sleep 700ms
Enter
Sleep 4s
Screenshot {out}/ask.png
Sleep 2s
Enter
Sleep 4s
"""),
    # A new sidechat left empty goes away, delete one, the session list without them, /sidechats.
    "manage": ("default", """
Sleep 1.5s
Down
Sleep 1s
Left
Sleep 1.5s
Down 2
Sleep 1.2s
Enter
Sleep 3s
Ctrl+X
Type "p"
Sleep 2s
Down
Sleep 1s
Left
Sleep 2s
Down
Sleep 1s
Ctrl+D
Sleep 1.5s
Ctrl+D
Sleep 2.5s
Escape
Sleep 1s
Ctrl+X
Type "l"
Sleep 3s
Screenshot {out}/list.png
Escape
Sleep 1s
Type "/sidechats"
Sleep 800ms
Enter
Sleep 3s
Screenshot {out}/dialog.png
Escape
Sleep 1.5s
"""),
}

for name, (prep, body) in TAPES.items():
    text = HEADER.format(out=OUT, name=name, prep=prep, b=B, main=plan["main"]) + body.format(out=OUT)
    (B / "tapes" / f"{name}.tape").write_text(text)
    print("wrote", name)
