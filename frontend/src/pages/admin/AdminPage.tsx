export function AdminPage({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="chrome flex h-[84px] shrink-0 items-center justify-between gap-4 divider-x px-7">
        <div className="min-w-0">
          <h1 className="display text-[24px] leading-none">{title}</h1>
          {subtitle && (
            <p className="mt-1.5 text-[13.5px] leading-snug text-[var(--text-faint)]">{subtitle}</p>
          )}
        </div>
        {actions}
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}
