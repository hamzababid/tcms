/**
 * Charts (docs/07 §5.12): counts in labels and tooltips, colours from the status tokens, an accessible
 * summary, and a "View data" table for every chart. Recharts is the documented chart library.
 */
import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { formatCount, formatPercent } from "@/lib/format";

export const STATUS_COLOR = {
  passed: "var(--status-pass-bar)",
  failed: "var(--status-fail-bar)",
  blocked: "var(--status-blocked-bar)",
  skipped: "var(--status-skip-bar)",
  not_run: "var(--status-notrun-bar)",
  accent: "var(--color-accent)",
} as const;

export interface Column<T> {
  key: string;
  label: string;
  value: (row: T) => ReactNode;
  numeric?: boolean;
}

/** A card with a chart and its data table (toggle). */
export function ChartCard<T>({
  title,
  description,
  summary,
  rows,
  columns,
  children,
  empty,
}: {
  title: string;
  description?: string;
  /** One sentence read by screen readers instead of the drawing. */
  summary: string;
  rows: T[];
  columns: Column<T>[];
  children: ReactNode;
  empty?: string;
}) {
  const [table, setTable] = useState(false);
  return (
    <Card
      title={title}
      {...(description ? { description } : {})}
      actions={
        rows.length ? (
          <Button
            variant="secondary"
            size="xs"
            aria-pressed={table}
            onClick={() => {
              setTable((t) => !t);
            }}
          >
            {table ? "View chart" : "View data"}
          </Button>
        ) : null
      }
    >
      {rows.length === 0 ? (
        <p className="py-6 text-center text-[13px] text-ink-secondary">
          {empty ?? "No data for these filters."}
        </p>
      ) : table ? (
        <DataGrid rows={rows} columns={columns} label={title} />
      ) : (
        <figure role="img" aria-label={summary} className="h-56">
          {children}
        </figure>
      )}
    </Card>
  );
}

export function DataGrid<T>({ rows, columns, label }: { rows: T[]; columns: Column<T>[]; label: string }) {
  return (
    <div className="max-h-72 overflow-auto">
      <table aria-label={`${label} data`} className="w-full text-left text-[12.5px]">
        <thead className="sticky top-0 bg-ground text-xs text-ink-secondary">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`px-2 py-1.5 font-medium ${c.numeric ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border">
              {columns.map((c) => (
                <td key={c.key} className={`px-2 py-1 ${c.numeric ? "tabular text-right" : ""}`}>
                  {c.value(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const axis = { fontSize: 11, fill: "var(--color-ink-secondary)" };

/** Stacked status bars, one per row (cycles, releases). */
export function StatusBars({
  data,
}: {
  data: { name: string; passed: number; failed: number; blocked: number; skipped: number; not_run: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" allowDecimals={false} tick={axis} />
        <YAxis type="category" dataKey="name" width={110} tick={axis} />
        <Tooltip formatter={(v) => formatCount(Number(v))} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {(["passed", "failed", "blocked", "skipped", "not_run"] as const).map((k) => (
          <Bar
            key={k}
            dataKey={k}
            name={
              {
                passed: "Passed",
                failed: "Failed",
                blocked: "Blocked",
                skipped: "Skipped",
                not_run: "Not run",
              }[k]
            }
            stackId="s"
            fill={STATUS_COLOR[k]}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Daily executed (bars) and pass rate (line, right axis). */
export function ExecutionTrend({
  data,
}: {
  data: { day: string; executed: number; passed: number; rate: number | null }[];
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ left: 0, right: 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="day" tick={axis} />
        <YAxis yAxisId="n" allowDecimals={false} tick={axis} />
        <YAxis
          yAxisId="p"
          orientation="right"
          domain={[0, 1]}
          tickFormatter={(v) => formatPercent(Number(v))}
          tick={axis}
        />
        <Tooltip
          formatter={(v, name, item) => {
            if (name === "Pass rate") {
              const row = item.payload as { executed: number; passed: number };
              return `${formatPercent(Number(v))} (${formatCount(row.passed)} of ${formatCount(row.executed)})`;
            }
            return formatCount(Number(v));
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar
          yAxisId="n"
          dataKey="executed"
          name="Executed"
          fill={STATUS_COLOR.accent}
          isAnimationActive={false}
        />
        <Line
          yAxisId="p"
          dataKey="rate"
          name="Pass rate"
          stroke={STATUS_COLOR.passed}
          dot={{ r: 3 }}
          connectNulls
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Daily P/F/B stacked bars. */
export function DailyStatus({
  data,
}: {
  data: { day: string; passed: number; failed: number; blocked: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ left: 0, right: 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="day" tick={axis} />
        <YAxis allowDecimals={false} tick={axis} />
        <Tooltip formatter={(v) => formatCount(Number(v))} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar
          dataKey="passed"
          name="Passed"
          stackId="s"
          fill={STATUS_COLOR.passed}
          isAnimationActive={false}
        />
        <Bar
          dataKey="failed"
          name="Failed"
          stackId="s"
          fill={STATUS_COLOR.failed}
          isAnimationActive={false}
        />
        <Bar
          dataKey="blocked"
          name="Blocked"
          stackId="s"
          fill={STATUS_COLOR.blocked}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Simple bars of one count per category (bug links per day, bugs by module). */
export function CountBars({ data, label }: { data: { name: string; value: number }[]; label: string }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ left: 0, right: 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" tick={axis} />
        <YAxis allowDecimals={false} tick={axis} />
        <Tooltip formatter={(v) => formatCount(Number(v))} />
        <Bar
          dataKey="value"
          name={label}
          fill={STATUS_COLOR.failed}
          maxBarSize={48}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
