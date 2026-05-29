"use client"

import * as React from "react"
import {
  Database, Layers, Cpu, HardDrive, CheckCircle2, XCircle,
  AlertTriangle, Loader2, Clock, Activity,
} from "lucide-react"
import { getStatus, getHealth } from "@/lib/api"
import { fetchUptimeSummary, type UptimeSite } from "@/lib/uptime"
import type { StatusResponse } from "@/lib/types"
import { StatusCard } from "@/components/StatusCard"

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const val = bytes / Math.pow(1024, i)
  return `${val.toFixed(val >= 100 ? 0 : 1)} ${units[i]}`
}

function formatVectors(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

type LiveStatus = "operational" | "degraded" | "down" | "checking"

export default function StatusPage() {
  // Upptime historical data (from GitHub)
  const [uptimeSites, setUptimeSites] = React.useState<UptimeSite[] | null>(null)
  const [uptimeError, setUptimeError] = React.useState(false)

  // Live status (direct polling)
  const [liveStatus, setLiveStatus] = React.useState<LiveStatus>("checking")
  const [indexStatus, setIndexStatus] = React.useState<StatusResponse | null>(null)
  const [lastChecked, setLastChecked] = React.useState<Date | null>(null)

  // Fetch Upptime data from GitHub
  React.useEffect(() => {
    fetchUptimeSummary()
      .then(setUptimeSites)
      .catch(() => setUptimeError(true))
  }, [])

  // Live polling
  React.useEffect(() => {
    let active = true
    async function poll() {
      try {
        const s = await getStatus()
        if (!active) return
        setIndexStatus(s)
        setLiveStatus("operational")
      } catch {
        if (!active) return
        try {
          await getHealth()
          if (!active) return
          setLiveStatus("degraded")
        } catch {
          if (!active) return
          setLiveStatus("down")
        }
      }
      if (active) setLastChecked(new Date())
    }
    poll()
    const interval = setInterval(poll, 10000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  const overallUp = uptimeSites?.every((s) => s.status === "up")
  const overallStatus = uptimeSites
    ? overallUp ? "operational" : "degraded"
    : liveStatus

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      {/* Headline */}
      <div className="text-center">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-border/60 px-4 py-1.5 text-xs">
          <span className={`inline-block h-2 w-2 rounded-full ${
            overallStatus === "operational" ? "bg-green-400 animate-pulse"
              : overallStatus === "degraded" ? "bg-amber-400"
              : overallStatus === "checking" ? "bg-muted-foreground animate-pulse"
              : "bg-red-400"
          }`} />
          <span className={
            overallStatus === "operational" ? "text-green-400"
              : overallStatus === "degraded" ? "text-amber-400"
              : overallStatus === "checking" ? "text-muted-foreground"
              : "text-red-400"
          }>
            {overallStatus === "operational" ? "All Systems Operational"
              : overallStatus === "degraded" ? "Partial System Degradation"
              : overallStatus === "checking" ? "Checking Systems..."
              : "System Outage"}
          </span>
        </div>
        <h1 className="font-display text-3xl font-bold tracking-tight">
          PixelRAG Status
        </h1>
        {lastChecked && (
          <p className="mt-2 text-xs text-muted-foreground">
            Live check: {lastChecked.toLocaleTimeString()}
          </p>
        )}
      </div>

      {/* Service rows — Upptime data if available, else live polling */}
      <div className="mt-10 overflow-hidden rounded-xl border border-border/60">
        <div className="border-b border-border/40 bg-muted/30 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Services
        </div>
        {uptimeSites && !uptimeError ? (
          uptimeSites.map((site) => (
            <UptimeServiceRow key={site.slug} site={site} />
          ))
        ) : (
          <>
            <LiveServiceRow name="API Server" status={liveStatus === "down" ? "down" : liveStatus === "checking" ? "checking" : "operational"} />
            <LiveServiceRow name="Search API" status={liveStatus} />
            <LiveServiceRow name="FAISS Index" status={liveStatus} />
            <LiveServiceRow name="Tile Serving" status={liveStatus} />
          </>
        )}
      </div>

      {/* Uptime history — 90 day bar from Upptime dailyMinutesDown */}
      {uptimeSites && uptimeSites.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            90-Day Uptime
          </h2>
          {uptimeSites.map((site) => (
            <div key={site.slug} className="mb-4">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="font-medium">{site.name}</span>
                <span className="text-muted-foreground">{site.uptime}</span>
              </div>
              <UptimeBar dailyMinutesDown={site.dailyMinutesDown} />
            </div>
          ))}
        </div>
      )}

      {/* No Upptime data yet — show setup hint */}
      {uptimeError && (
        <div className="mt-8 rounded-xl border border-border/60 bg-muted/30 px-5 py-4 text-center text-xs text-muted-foreground">
          <Activity className="mx-auto mb-2 h-5 w-5" />
          <p>Historical uptime data will appear here once GitHub Actions starts running.</p>
          <p className="mt-1">Push to GitHub and trigger the Uptime CI workflow to begin monitoring.</p>
        </div>
      )}

      {/* Index details */}
      {indexStatus && (
        <>
          <h2 className="mt-12 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Index Details
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatusCard
              label="Total Vectors"
              value={formatVectors(indexStatus.total_vectors)}
              sub={`${indexStatus.total_vectors.toLocaleString()} exact`}
              icon={<Database className="h-3.5 w-3.5" />}
            />
            <StatusCard
              label="Dimension"
              value={String(indexStatus.dimension)}
              icon={<Layers className="h-3.5 w-3.5" />}
            />
            <StatusCard
              label="Model"
              value={indexStatus.model.split("/").pop() ?? indexStatus.model}
              sub={indexStatus.model}
              icon={<Cpu className="h-3.5 w-3.5" />}
            />
            <StatusCard
              label="Index Size"
              value={formatBytes(indexStatus.index_size_bytes)}
              sub={`+ ${formatBytes(indexStatus.metadata_size_bytes)} metadata`}
              icon={<HardDrive className="h-3.5 w-3.5" />}
            />
          </div>

          <div className="mt-6 overflow-hidden rounded-xl border border-border/60">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Parameter</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <ConfigRow label="nlist" value={String(indexStatus.nlist)} />
                <ConfigRow label="nprobe" value={String(indexStatus.nprobe)} />
                <ConfigRow label="Built at" value={indexStatus.index_built_at} />
                <ConfigRow label="Index directory" value={indexStatus.index_dir} mono />
                <ConfigRow label="Tiles directory" value={indexStatus.tiles_dir} mono />
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function UptimeServiceRow({ site }: { site: UptimeSite }) {
  const isUp = site.status === "up"
  return (
    <div className="flex items-center justify-between border-b border-border/40 px-5 py-3.5 last:border-b-0">
      <div>
        <div className="text-sm font-medium">{site.name}</div>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span>{site.uptime} uptime</span>
          <span>·</span>
          <span>{site.time}ms avg</span>
        </div>
      </div>
      <div className={`flex items-center gap-2 text-xs font-medium ${isUp ? "text-green-400" : "text-red-400"}`}>
        {isUp ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
        {isUp ? "Operational" : "Down"}
      </div>
    </div>
  )
}

function LiveServiceRow({ name, status }: { name: string; status: LiveStatus }) {
  const config = {
    operational: { icon: CheckCircle2, label: "Operational", color: "text-green-400" },
    degraded: { icon: AlertTriangle, label: "Starting", color: "text-amber-400" },
    down: { icon: XCircle, label: "Down", color: "text-red-400" },
    checking: { icon: Loader2, label: "Checking", color: "text-muted-foreground" },
  }[status]
  const Icon = config.icon
  return (
    <div className="flex items-center justify-between border-b border-border/40 px-5 py-3.5 last:border-b-0">
      <div className="text-sm font-medium">{name}</div>
      <div className={`flex items-center gap-2 text-xs font-medium ${config.color}`}>
        <Icon className={`h-4 w-4 ${status === "checking" ? "animate-spin" : ""}`} />
        {config.label}
      </div>
    </div>
  )
}

function UptimeBar({ dailyMinutesDown }: { dailyMinutesDown: Record<string, number> }) {
  const days: { date: string; down: number }[] = []
  const now = new Date()
  for (let i = 89; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    days.push({ date: key, down: dailyMinutesDown[key] ?? 0 })
  }

  return (
    <div className="flex h-8 gap-px overflow-hidden rounded-lg">
      {days.map((day) => {
        const bg = day.down === 0 ? "bg-green-500"
          : day.down < 30 ? "bg-amber-500"
          : "bg-red-500"
        return (
          <div
            key={day.date}
            className={`flex-1 ${bg} transition-colors`}
            title={`${day.date}: ${day.down === 0 ? "No downtime" : `${day.down} min down`}`}
          />
        )
      })}
    </div>
  )
}

function ConfigRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <tr>
      <td className="px-4 py-2.5 font-medium text-muted-foreground">{label}</td>
      <td className={`px-4 py-2.5 ${mono ? "font-mono text-xs" : ""}`}>{value}</td>
    </tr>
  )
}
