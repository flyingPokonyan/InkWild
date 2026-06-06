interface Props {
  title: string;
  sub?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, sub, actions }: Props) {
  return (
    <div className="page-hd">
      <div>
        <h1 className="page-title">{title}</h1>
        {sub && <div className="page-sub">{sub}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
