import PageHeader, { PageContainer } from '../components/PageHeader'
import Button from '../components/Button'
import { ROUTES } from '../data/content'

/* Shown for any URL that doesn't match a screen, so visitors are never stuck. */
export default function NotFoundPage() {
  return (
    <PageContainer>
      <PageHeader
        title="Page not found"
        documentTitle="Page not found"
        intro="The page you’re looking for doesn’t exist or may have moved."
      />
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Button to={ROUTES.home}>Go to the homepage</Button>
        <Button to={ROUTES.diagnose} variant="secondary">
          Diagnose a Problem
        </Button>
      </div>
    </PageContainer>
  )
}
