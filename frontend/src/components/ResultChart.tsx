import {
  BarChart,
  Bar,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Props {
  payload: any;
}

function asArray(value: any): any[] | null {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object" && Array.isArray(value.data)) return value.data;
  return null;
}

function inferChartData(payload: any): any[] | null {
  for (const key of Object.keys(payload || {})) {
    const arr = asArray(payload[key]);
    if (arr && arr.length > 0) {
      return arr.map((item, i) =>
        typeof item === "object" ? item : { index: i, value: item }
      );
    }
  }
  return null;
}

function ResultChart({ payload }: Props) {
  const data = inferChartData(payload);
  if (!data || data.length === 0) return null;

  const first = data[0];
  const keys = Object.keys(first).filter(
    (k) => typeof first[k] === "number"
  );

  if (keys.length === 0) return null;

  // If multiple numeric keys, use a bar chart; otherwise a line chart.
  const Chart = keys.length > 1 ? BarChart : LineChart;

  return (
    <div className="chart-wrapper" style={{ height: 220, marginTop: 12 }}>
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={Object.keys(first).find((k) => typeof first[k] === "string") || "index"} />
          <YAxis />
          <Tooltip />
          <Legend />
          {keys.map((k, i) =>
            Chart === BarChart ? (
              <Bar key={k} dataKey={k} fill={i === 0 ? "#3b82f6" : "#10b981"} />
            ) : (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                stroke={i === 0 ? "#3b82f6" : "#10b981"}
                dot={false}
              />
            )
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}

export default ResultChart;
