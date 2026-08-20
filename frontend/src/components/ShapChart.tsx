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

const FRAUD_RED = "#B81514"; // ct-danger-primary
const LEGIT_GREEN = "#6EA335"; // sr-green-600

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
              tick={{ fill: "#757575", fontSize: 11 }}
              axisLine={{ stroke: "#E6E6E6" }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={190}
              tick={{ fill: "#3D3D3D", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <ReferenceLine x={0} stroke="#CCCCCC" />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.04)" }}
              contentStyle={{
                background: "#FFFFFF",
                border: "1px solid #E6E6E6",
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
