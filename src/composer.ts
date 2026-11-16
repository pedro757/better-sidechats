// The session composer (the Subagents / Shell / Terminals menu below the transcript) has no plugin API for tabs: its
// tabs register through an internal Solid context. The `session.composer.top` slot renders right above the composer,
// under the same Solid owner, so a component in that slot can find the composer's tab registry by walking the owner
// tree, and place its tab body inside the composer's box by walking the renderable tree.
//
// Both walks rely on OpenCode internals, so every step checks what it finds and gives up quietly. When they fail the
// Sidechats tab is missing and the /sidechats dialog still works.
import type { BaseRenderable } from "@opentui/core"

export interface ComposerHint {
  readonly label: string
  readonly shortcut: string
}

export interface ComposerTab {
  readonly id: string
  readonly label: string
  readonly hints?: () => ComposerHint[]
}

/** The composer's tab registry: what its built-in tabs use. */
export interface ComposerApi {
  register(tab: ComposerTab): () => void
  active(id: string): boolean
  close(): void
}

interface OwnerLike {
  readonly owner?: OwnerLike | null
  readonly owned?: readonly OwnerLike[] | null
  readonly context?: Record<PropertyKey, unknown> | null
}

function isComposerApi(value: unknown): value is ComposerApi {
  if (!value || typeof value !== "object") return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.register === "function" &&
    typeof candidate.active === "function" &&
    typeof candidate.close === "function"
  )
}

function provided(owner: OwnerLike): ComposerApi | undefined {
  const context = owner.context
  if (!context) return
  for (const key of Object.getOwnPropertySymbols(context)) {
    const value = context[key]
    if (isComposerApi(value)) return value
  }
}

/**
 * Finds the composer next to `start` (the slot component's Solid owner). Searches each ancestor's descendants
 * breadth first, so the nearest composer wins. Contexts are inherited, so the ancestors of `start` carry only contexts
 * provided above the composer and are skipped.
 */
export function findComposer(start: unknown, limit = 50_000): ComposerApi | undefined {
  const origin = start as OwnerLike | null | undefined
  if (!origin) return
  const inherited = new Set<unknown>()
  for (let owner: OwnerLike | null | undefined = origin; owner; owner = owner.owner) {
    const context = owner.context
    if (context) for (const key of Object.getOwnPropertySymbols(context)) inherited.add(context[key])
  }
  const seen = new Set<OwnerLike>()
  let budget = limit
  for (let ancestor: OwnerLike | null | undefined = origin.owner; ancestor && budget > 0; ancestor = ancestor.owner) {
    const queue: OwnerLike[] = [ancestor]
    for (let index = 0; index < queue.length && budget > 0; index++) {
      const owner = queue[index]!
      if (seen.has(owner)) continue
      seen.add(owner)
      budget--
      const api = provided(owner)
      if (api && !inherited.has(api)) return api
      for (const child of owner.owned ?? []) if (!seen.has(child)) queue.push(child)
    }
  }
}

interface NodeLike {
  readonly parent: NodeLike | null
  readonly isDestroyed?: boolean
  readonly plainText?: unknown
  getChildren(): NodeLike[]
  insertBefore(node: unknown, anchor: unknown): unknown
}

function findText(root: NodeLike, text: string, skip: unknown, depth = 0): NodeLike | undefined {
  if (depth > 40 || root === skip) return
  if (typeof root.plainText === "string" && root.plainText === text) return root
  for (const child of root.getChildren?.() ?? []) {
    const found = findText(child, text, skip, depth + 1)
    if (found) return found
  }
}

/**
 * The tab's label in the nearest composer, which the composer renders once the tab is registered. Searches outward
 * from `anchor` (a node of the slot), skipping `panel`.
 */
function findLabel(anchor: BaseRenderable, panel: BaseRenderable, label: string): NodeLike | undefined {
  for (
    let scope = (anchor as unknown as NodeLike).parent, depth = 0;
    scope && depth < 6;
    scope = scope.parent, depth++
  ) {
    const text = findText(scope, label, panel)
    if (text) return text
  }
}

/**
 * Puts `panel` in the composer's body, right after its header row (the tab labels and `esc`), where the built-in tabs
 * render their lists.
 */
export function placeInComposer(anchor: BaseRenderable, panel: BaseRenderable, label: string): boolean {
  const node = panel as unknown as NodeLike
  const text = findLabel(anchor, panel, label)
  // label text -> tab label row -> header row -> composer body
  const header = text?.parent?.parent
  const body = header?.parent
  if (!header || !body || body.isDestroyed) return false
  const children = body.getChildren()
  const index = children.indexOf(header)
  const next = children[index + 1]
  if (index < 0 || !next) return false
  if (node.parent === body && children[index + 1] === node) return true
  if (node.parent) return false
  body.insertBefore(panel, next)
  return node.parent === body
}

/**
 * Whether the tab's label is the last one in the composer, or undefined when the label isn't rendered. A tab that
 * registers later (Terminals waits for the terminal service) lands after it.
 */
export function isLastTab(anchor: BaseRenderable, panel: BaseRenderable, label: string): boolean | undefined {
  const text = findLabel(anchor, panel, label)
  const labels = text?.parent?.getChildren()
  if (!text || !labels) return
  return labels[labels.length - 1] === text
}

/** Takes `panel` out of the composer and frees it. Safe after the composer itself was destroyed. */
export function removeFromComposer(panel: BaseRenderable) {
  const node = panel as unknown as NodeLike
  try {
    const parent = node.parent as unknown as { remove?(child: unknown): void; isDestroyed?: boolean } | null
    if (parent && !parent.isDestroyed) parent.remove?.(panel)
  } catch {}
  try {
    if (!node.isDestroyed) panel.destroyRecursively()
  } catch {}
}
