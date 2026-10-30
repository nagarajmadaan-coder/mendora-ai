import type { ReactNode } from 'react'
import PageHeader, { PageContainer } from './PageHeader'
import Icon from './Icon'

/* Shared layout for the Sign in and Create account screens. */
export default function AuthCard({
  title,
  intro,
  documentTitle,
  children,
}: {
  title: string
  intro: ReactNode
  documentTitle: string
  children: ReactNode
}) {
  return (
    <PageContainer>
      <div className="mx-auto max-w-md">
        <PageHeader title={title} documentTitle={documentTitle} intro={intro} />
        <div className="mt-8 rounded-2xl border border-navy-900/10 bg-white p-5 shadow-sm sm:p-8">{children}</div>
        <p className="mt-5 flex items-start gap-2 text-xs leading-relaxed text-navy-600">
          <Icon name="lock" className="mt-px size-3.5 shrink-0" />
          Passwords are stored securely as one-way hashes and are never shown to anyone, including MENDORA staff.
        </p>
      </div>
    </PageContainer>
  )
}
