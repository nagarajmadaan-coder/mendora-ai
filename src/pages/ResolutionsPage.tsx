import PageHeader, { PageContainer } from '../components/PageHeader'
import ResolutionCard from '../components/ResolutionCard'
import Button from '../components/Button'
import Badge from '../components/Badge'
import Icon from '../components/Icon'
import { RESOLUTIONS, ROUTES, getTrade, requestUrl } from '../data/content'
import { useIntake } from '../state/IntakeContext'

/*
  Resolution Options screen (URL: /resolutions).
  Shows the three options, each with an honest label for how much of it works today.
  - If the visitor has a saved request (this session), it is summarised at the top.
  - If not, an empty state invites them to describe a problem first.
*/
export default function ResolutionsPage() {
  const { lastRequest } = useIntake()
  const diagnosis = lastRequest?.diagnosis
  const statusLine = !lastRequest
    ? ''
    : lastRequest.safety.risk_level === 'high'
      ? 'High risk: please follow the safety advice and contact a qualified professional. AI Fix is not available for this request.'
      : diagnosis
        ? diagnosis.professional_recommended
          ? 'Assessed: the AI recommended a professional for this problem.'
          : 'Assessed. Once these options are built, they will be matched to your assessment.'
        : lastRequest.safety.risk_level === 'medium'
          ? 'A safety check is needed: a professional is recommended, and AI Fix (DIY) is switched off.'
          : 'Not assessed yet. Open the request to get an AI diagnosis.'

  return (
    <PageContainer>
      <PageHeader
        title="Resolution options"
        documentTitle="Resolution options"
        aside={
          <Badge tone="amber" icon="clock">
            Prototype — partly available
          </Badge>
        }
        intro="After the safety check, choose a route. Payments are a sandbox demonstration (no real money), and no live calls are connected. The AI diagnosis needs an AI provider, which isn’t connected yet."
      />

      {/* Request summary, or an empty state */}
      <div className="mt-8">
        {lastRequest ? (
          <div className="flex flex-col gap-4 rounded-2xl border border-navy-900/10 bg-white p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
            <div className="flex items-start gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-navy-900 text-teal-300">
                <Icon name={getTrade(lastRequest.trade.id).icon} className="size-5" />
              </span>
              <div className="min-w-0">
                <p className="font-semibold text-navy-900">Your {lastRequest.trade.name.toLowerCase()} request</p>
                <p className="mt-0.5 line-clamp-2 text-sm break-words text-navy-600">{lastRequest.description}</p>
                <p className="mt-2 text-sm text-amber-800">{statusLine}</p>
              </div>
            </div>
            <Button to={requestUrl(lastRequest.request_id)} variant="secondary" className="shrink-0">
              View request
            </Button>
          </div>
        ) : (
          <div className="flex flex-col items-start gap-4 rounded-2xl border border-dashed border-navy-900/20 bg-white p-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-700">
                <Icon name="message" className="size-5" />
              </span>
              <div>
                <p className="font-semibold text-navy-900">You haven’t described a problem yet</p>
                <p className="mt-0.5 text-sm text-navy-600">
                  Start a repair request first. Once these options are built, they will be matched to your assessment.
                </p>
              </div>
            </div>
            <Button to={ROUTES.diagnose} className="shrink-0">
              Diagnose a Problem
            </Button>
          </div>
        )}
      </div>

      <ul className="mt-8 grid gap-5 md:grid-cols-3">
        {RESOLUTIONS.map((resolution) => (
          <li key={resolution.id}>
            <ResolutionCard resolution={resolution} detailed />
          </li>
        ))}
      </ul>

      <div className="mt-8 flex items-start gap-3 rounded-2xl border border-navy-900/10 bg-white p-5 sm:p-6">
        <Icon name="shield" className="mt-0.5 size-6 shrink-0 text-teal-700" />
        <div>
          <h2 className="font-semibold text-navy-900">Safety decides which options appear</h2>
          <p className="mt-1 leading-relaxed text-navy-600">
            AI Fix will only be offered for low-risk problems. Sparking electrics, suspected gas leaks, smoke and
            structural damage will never get DIY instructions — only advice to get safe and contact a professional.
          </p>
          <Button to={ROUTES.about} variant="secondary" className="mt-4">
            About MENDORA &amp; safety
          </Button>
        </div>
      </div>
    </PageContainer>
  )
}
