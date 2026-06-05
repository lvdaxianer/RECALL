interface ErrorStateProps {
  title: string;
  description?: string;
  onRetry?: () => void;
}

export function ErrorState({ title, description, onRetry }: ErrorStateProps) {
  return (
    <div className="state-surface state-surface--error" role="alert">
      <div>
        <strong>{title}</strong>
        {description ? <span>{description}</span> : null}
      </div>
      {onRetry ? (
        <button className="button button--secondary" type="button" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}
