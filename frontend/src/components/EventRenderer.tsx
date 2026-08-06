import ResultChart from "./ResultChart";

interface Props {
  event: any;
}

function EventRenderer({ event }: Props) {
  const data = event.data || {};

  if (event.type === "tool_call") {
    return (
      <div className="tool-call">
        <span>Tool call:</span> <strong>{data.name}</strong>
        <pre>{JSON.stringify(data.arguments, null, 2)}</pre>
      </div>
    );
  }

  if (event.type === "tool_result") {
    return (
      <div className="tool-result">
        <span>Tool result:</span> <strong>{data.name}</strong>
        {data.success ? (
          <>
            <pre>{JSON.stringify(data.payload, null, 2)}</pre>
            <ResultChart payload={data.payload} />
          </>
        ) : (
          <div className="error">{data.error}</div>
        )}
      </div>
    );
  }

  return (
    <div className="event">
      <pre>{JSON.stringify(event, null, 2)}</pre>
    </div>
  );
}

export default EventRenderer;
