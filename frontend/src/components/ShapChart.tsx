import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ShapFeature } from "@/lib/types";

const FRAUD_RED = "#ef4444";
const LEGIT_GREEN = "#10b981";

export function ShapChart({ features }: { features: ShapFeature[] }) {
  const data = [...features]
    .sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value))
    .map((f) => ({ ...f, name: f.label }));

  return (
    <div>
      <div className="h-56 w-full">
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
            <XAxis
              type="number"
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              axisLine={{ stroke: "#1e293b" }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={190}
              tick={{ fill: "#cbd5e1", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <ReferenceLine x={0} stroke="#334155" />
            <Tooltip
              cursor={{ fill: "rgba(148,163,184,0.06)" }}
              contentStyle={{
                background: "#0f172a",
                border: "1px solid #1e293b",
                borderRadius: 6,
                fontSize: 12,
              }}
              formatter={(value: number) => [value.toFixed(3), "SHAP contribution"]}
            />
            <Bar dataKey="shap_value" radius={[3, 3, 3, 3]} barSize={16}>
              {data.map((entry) => (
                <Cell
                  key={entry.feature}
                  fill={entry.shap_value > 0 ? FRAUD_RED : LEGIT_GREEN}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 space-y-1.5">
        {data.map((f) => (
          <li key={f.feature} className="flex items-start gap-2 text-sm">
            <span
              className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                f.shap_value > 0 ? "bg-danger" : "bg-success"
              }`}
            />
            <span className="text-muted-foreground">{f.explanation}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">
        Red bars push the decision toward fraud; green bars push toward legitimate.
      </p>
    </div>
  );
}
