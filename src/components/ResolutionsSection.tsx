import Section from './Section'
import ResolutionCard from './ResolutionCard'
import Button from './Button'
import Icon from './Icon'
import { RESOLUTIONS, ROUTES } from '../data/content'

export default function ResolutionsSection() {
  return (
    <Section
      id="resolutions"
      eyebrow="Resolutions"
      title="Choose how your problem gets solved"
      intro="After the assessment, you will pick the route that fits the problem, your skills and your time. These options are still being built."
    >
      <div className="grid gap-5 md:grid-cols-3">
        {RESOLUTIONS.map((resolution) => (
          <ResolutionCard key={resolution.id} resolution={resolution} />
        ))}
      </div>
      <div className="mt-8">
        <Button to={ROUTES.resolutions} variant="secondary">
          Compare resolution options
          <Icon name="arrowRight" className="size-4" />
        </Button>
      </div>
    </Section>
  )
}
