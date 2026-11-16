# Recording the demo

The GIFs and screenshots in `media/` come from a sandboxed OpenCode with made-up sessions. Nothing in it touches
a real OpenCode install: it uses its own XDG config, data and state directories under `/tmp/bsc-demo` (or
`$BSC_DEMO`) and its own server port, and it talks to a local mock model instead of a provider.

| File           | What it does                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------- |
| `bootstrap.sh` | Creates the sandbox: its config, a demo git project (`acme-web`) and a copy of the plugin. `OPENCODE_BIN` picks the OpenCode binary |
| `mock.py`      | An OpenAI-compatible chat completions server. The last message you typed picks a scenario: answer, read a file and keep streaming (running), or edit a file (a permission in a sidechat) |
| `setup.py`     | Creates the demo sessions and two sidechats of the main session, backdates them in the sandbox database, and snapshots the sandbox |
| `prep.py`      | Restores the snapshot before each recording; for `btw`, starts a long turn in the main session            |
| `tapes.py`     | Writes the [VHS](https://github.com/charmbracelet/vhs) tapes                                              |

```sh
demo/bootstrap.sh
python3 /tmp/bsc-demo/mock/mock.py 47590 &      # keep it running while recording
python3 /tmp/bsc-demo/setup.py
cd /tmp/bsc-demo && python3 tapes.py
for t in btw tab bring-back edit manage; do
  mise exec vhs@latest ttyd@latest -- vhs tapes/$t.tape
done
```

The output lands in `/tmp/bsc-demo/media`. Stop the sandbox server afterwards with
`source /tmp/bsc-demo/env.sh && opencode service stop`.
