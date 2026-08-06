interface Props {
  requestId: string;
  toolName: string;
  arguments: Record<string, any>;
  onApprove: () => void;
  onReject: () => void;
}

function ApprovalCard({ toolName, arguments: args, onApprove, onReject }: Props) {
  return (
    <div className="approval-card">
      <div className="approval-title">Approval required</div>
      <div className="approval-body">
        Tool: <strong>{toolName}</strong>
        <pre>{JSON.stringify(args, null, 2)}</pre>
      </div>
      <div className="approval-actions">
        <button className="approve" onClick={onApprove}>Approve</button>
        <button className="reject" onClick={onReject}>Reject</button>
      </div>
    </div>
  );
}

export default ApprovalCard;
