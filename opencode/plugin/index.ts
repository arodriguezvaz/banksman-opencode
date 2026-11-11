import { execFile } from "node:child_process"
import { promisify } from "node:util"

const run = promisify(execFile)
const BANKSMAN = process.env.BANKSMAN_BIN ?? "/home/andres/.local/bin/banksman"

type Lease = { id: string; resource: string; serial?: string }

// The leases held by this plugin instance, one per OpenCode session.
const leases = new Map<string, Lease>()

function environment(sessionID: string) {
  return {
    ...process.env,
    OPENCODE: "1",
    AI_AGENT: "opencode",
    OPENCODE_SESSION_ID: sessionID,
  }
}

async function banksman(args: string[], sessionID: string, cwd?: string) {
  return run(BANKSMAN, args, {
    cwd: cwd || process.cwd(),
    env: environment(sessionID),
    timeout: 240_000,
    maxBuffer: 16 * 1024 * 1024,
  })
}

async function acquire(sessionID: string, cwd?: string): Promise<Lease> {
  const { stdout } = await banksman(
    [
      "acquire",
      "--where", "kind=emulator",
      "--start",
      "--for", `opencode:${sessionID}`,
      "--expect", "30m",
      "--wait", "25s",
      "--json",
    ],
    sessionID,
    cwd,
  )
  const parsed = JSON.parse(stdout)
  const part = parsed?.parts?.[0]
  if (!part?.lease_id) throw new Error(`banksman no devolvió un lease: ${stdout}`)
  return { id: part.lease_id, resource: part.resource, serial: part.serial ?? undefined }
}

async function held(sessionID: string, cwd?: string): Promise<Lease | undefined> {
  const { stdout } = await banksman(["held", "--json"], sessionID, cwd)
  const parsed = JSON.parse(stdout)
  const lease = parsed?.leases?.[0]
  if (!lease?.lease_id) return undefined
  return { id: lease.lease_id, resource: lease.resource, serial: lease.serial ?? undefined }
}

async function ensure(sessionID: string, cwd?: string): Promise<Lease> {
  const current = leases.get(sessionID)
  if (current) {
    // The lease may have been released by hand, or the plugin may have been reloaded. Do not
    // inject a stale token: adopt the session's current lease, or acquire a new one.
    const own = await held(sessionID, cwd).catch(() => undefined)
    if (own && own.id === current.id) return current
    leases.delete(sessionID)
  }
  try {
    const lease = await acquire(sessionID, cwd)
    leases.set(sessionID, lease)
    return lease
  } catch (error) {
    // If this session already holds a lease, adopt it instead of asking for a second one.
    const lease = await held(sessionID, cwd).catch(() => undefined)
    if (lease) {
      leases.set(sessionID, lease)
      return lease
    }
    throw error
  }
}

async function release(sessionID: string) {
  const lease = leases.get(sessionID)
  if (!lease) return
  leases.delete(sessionID)
  try {
    // No --end: the AVD stays running for the next session.
    await banksman(["release", "--lease", lease.id], sessionID)
  } catch (error) {
    console.error("banksman-opencode: no pude liberar el lease", error)
  }
}

function segments(command: string): string[][] {
  return command
    .split(/&&|\|\||;|\|/)
    .map((part) => part.trim().split(/\s+/).filter(Boolean))
}

function programIndex(words: string[]): number {
  let i = 0
  while (i < words.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i])) i++
  if (words[i] === "timeout") {
    i++
    while (i < words.length && words[i].startsWith("-")) i++
    i++
  } else if (words[i] === "env") {
    i++
    while (i < words.length && (words[i].includes("=") || words[i].startsWith("-"))) i++
  }
  return i
}

function isDeviceCommand(command: string): boolean {
  for (const words of segments(command)) {
    const start = programIndex(words)
    const program = (words[start] ?? "").split("/").pop()
    const rest = words.slice(start + 1)
    if (program === "banksman") continue
    if (program === "adb") {
      let j = 0
      while (j < rest.length) {
        if (["-s", "-t", "-P", "-H", "-L"].includes(rest[j])) {
          j += 2
          continue
        }
        if (rest[j].startsWith("-")) {
          j++
          continue
        }
        break
      }
      const subcommand = rest[j] ?? ""
      if (
        ["devices", "version", "help", "--help", "start-server", "wait-for-device", "get-state"].includes(
          subcommand,
        )
      ) {
        continue
      }
      return true
    }
    const joined = rest.join(" ")
    if (program === "gradlew" || program === "gradle") {
      if (/\b(?:connected\w*|install\w*|uninstall\w*)\b/.test(joined)) return true
    }
    if (["maestro", "flutter", "react-native", "expo"].includes(program ?? "")) {
      if (/\b(?:test|record|studio|hierarchy|run|android)\b/.test(joined)) return true
    }
  }
  return false
}

function quote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`
}

export default {
  id: "banksman-opencode",
  async setup(ctx: any) {
    await ctx.tool.hook("execute.before", async (event: any) => {
      const command: string | undefined = event.input?.command
      if (typeof command !== "string") return
      if (!isDeviceCommand(command)) return
      const sessionID: string | undefined = event.sessionID ?? event.input?.sessionID
      if (!sessionID) return
      const lease = await ensure(sessionID, event.input?.cwd)
      const exports = [`BANKSMAN_LEASE=${quote(lease.id)}`]
      if (lease.serial) exports.push(`ANDROID_SERIAL=${quote(lease.serial)}`)
      event.input.command = `export ${exports.join(" ")}; ${command}`
    })

    const controller = new AbortController()
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({
          types: ["session.idle", "session.deleted"],
          signal: controller.signal,
        })) {
          const sessionID = event?.data?.sessionID
          if (sessionID) await release(sessionID)
        }
      } catch (error) {
        if (!controller.signal.aborted) console.error("banksman-opencode: event stream", error)
      }
    })()

    return () => {
      controller.abort()
      for (const sessionID of [...leases.keys()]) void release(sessionID)
    }
  },
}
