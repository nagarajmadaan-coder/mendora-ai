import { useEffect } from 'react'
import Hero from '../components/Hero'
import ServicesSection from '../components/ServicesSection'
import HowItWorks from '../components/HowItWorks'
import ResolutionsSection from '../components/ResolutionsSection'
import SafetySection from '../components/SafetySection'

// The homepage is just the sections stacked in order.
export default function HomePage() {
  useEffect(() => {
    document.title = 'MENDORA AI — Home repair, diagnosed'
  }, [])

  return (
    <>
      <Hero />
      <ServicesSection />
      <HowItWorks />
      <ResolutionsSection />
      <SafetySection />
    </>
  )
}
