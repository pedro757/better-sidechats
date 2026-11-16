#!/usr/bin/env bash
# Builds the recording sandbox in $BSC_DEMO (default /tmp/bsc-demo): a separate OpenCode (its own XDG config, data and
# state, and its own server port), a demo git project, a mock model and a copy of this plugin. Your real OpenCode is
# not touched. OPENCODE_BIN picks the OpenCode binary (default: the `opencode` on PATH).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
plugin=$(cd "$here/.." && pwd)
B=${BSC_DEMO:-/tmp/bsc-demo}
opencode_bin=${OPENCODE_BIN:-$(command -v opencode)}

mkdir -p "$B"/home/{config,data,state,cache}/opencode "$B"/mock "$B"/media "$B"/bin
# Resolved now: the sandbox's XDG directories would hide a version manager's config later.
ln -sfn "$opencode_bin" "$B/bin/opencode"
cp "$here/mock.py" "$B/mock/"
cp "$here/setup.py" "$here/prep.py" "$here/tapes.py" "$B/"

cat > "$B/env.sh" <<EOF
export BSC_DEMO=$B
export PATH=$B/bin:\$PATH
export XDG_CONFIG_HOME=$B/home/config XDG_DATA_HOME=$B/home/data
export XDG_STATE_HOME=$B/home/state XDG_CACHE_HOME=$B/home/cache
unset OPENCODE_CLI_CONFIG_CONTENT
EOF

# Its own server port, so it never attaches to a running OpenCode.
echo '{ "port": 47591 }' > "$B/home/config/opencode/service.json"

cat > "$B/home/config/opencode/opencode.jsonc" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "update": "disable",
  "share": "disabled",
  "snapshots": false,
  "model": "mock/demo",
  "agents": { "title": { "model": "mock/demo" } },
  "permissions": [{ "action": "shell", "resource": "*", "effect": "allow" }],
  "providers": {
    "mock": {
      "name": "Demo",
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": { "baseURL": "http://127.0.0.1:47590/v1", "apiKey": "demo" },
      "models": {
        "demo": { "name": "Demo model", "capabilities": { "tools": true }, "limit": { "context": 200000, "output": 32000 } }
      }
    }
  }
}
EOF

cat > "$B/home/config/opencode/cli.json" <<'EOF'
{
  "theme": { "name": "tokyonight", "mode": "dark" },
  "plugins": ["-opencode.notifications"],
  "tabs": { "enabled": false, "mode": "off" },
  "session": { "sidebar": "hide" },
  "mouse": false
}
EOF

rm -rf "$B/home/config/opencode/plugins/better-sidechats"
mkdir -p "$B/home/config/opencode/plugins/better-sidechats"
cp -r "$plugin/tui.tsx" "$plugin/index.ts" "$plugin/src" "$B/home/config/opencode/plugins/better-sidechats/"

if [ ! -d "$B/acme-web/.git" ]; then
  mkdir -p "$B/acme-web/src/checkout" "$B/acme-web/src/payments"
  printf '# acme-web\n\nThe Acme storefront.\n' > "$B/acme-web/README.md"
  cat > "$B/acme-web/src/checkout/cart.ts" <<'EOF'
export interface LineItem {
  sku: string
  quantity: number
  unitPrice: number
}

export function cartTotal(items: LineItem[]): number {
  return items.reduce((total, item) => total + item.quantity * item.unitPrice, 0)
}
EOF
  cat > "$B/acme-web/src/payments/client.ts" <<'EOF'
import { LegacyPayments } from "legacy-payments"

export const payments = new LegacyPayments({ apiKey: process.env.PAYMENTS_KEY! })

export function charge(amountCents: number, token: string) {
  return payments.charges.create({ amount: amountCents / 100, source: token })
}
EOF
  cat > "$B/acme-web/src/payments/webhooks.ts" <<'EOF'
import { createHmac, timingSafeEqual } from "node:crypto"

const TOLERANCE_SECONDS = 300

export function verifySignature(payload: string, header: string, secret: string, now = Date.now()) {
  const [timestamp, signature] = header.split(",")
  if (Math.abs(now / 1000 - Number(timestamp)) > TOLERANCE_SECONDS) return false
  const expected = createHmac("sha256", secret).update(`${timestamp}.${payload}`).digest("hex")
  return timingSafeEqual(Buffer.from(signature), Buffer.from(expected))
}
EOF
  (cd "$B/acme-web" && git init -q && git add . &&
    git -c user.name=demo -c user.email=demo@example.com commit -qm init)
fi
echo '{}' > "$B/mock/scenarios.json"
echo "Sandbox ready in $B"
