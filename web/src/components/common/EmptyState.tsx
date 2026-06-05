interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="state-surface state-surface--center">
      <strong>{title}</strong>
      {description ? <span>{description}</span> : null}
    </div>
  );
}
