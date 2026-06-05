import type { PropsWithChildren } from "react";

interface SectionCardProps {
  title?: string;
}

export function SectionCard({ title, children }: PropsWithChildren<SectionCardProps>) {
  return (
    <section className="section-card">
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}
