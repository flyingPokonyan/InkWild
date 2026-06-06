import clsx from "clsx";

interface Props {
  title?: React.ReactNode;
  sub?: React.ReactNode;
  actions?: React.ReactNode;
  flush?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
  footer?: React.ReactNode;
}

export function Card({ title, sub, actions, flush, children, style, footer }: Props) {
  return (
    <div className="card" style={style}>
      {(title || actions) && (
        <div className="card-hd">
          <div>
            {title && <h3>{title}</h3>}
            {sub && <div className="card-hd-sub" style={{ marginTop: 2 }}>{sub}</div>}
          </div>
          {actions && <div className="cluster">{actions}</div>}
        </div>
      )}
      <div className={clsx("card-bd", flush && "flush")}>{children}</div>
      {footer && <div className="card-ft">{footer}</div>}
    </div>
  );
}
