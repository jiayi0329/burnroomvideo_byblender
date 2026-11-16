import type { ReactNode } from 'react'
export function PageHeading({
  number,
  title,
  description,
  children,
}: {
  number: string
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">工作流程 / {number}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  )
}
