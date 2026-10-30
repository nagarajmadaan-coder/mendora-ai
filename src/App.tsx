import Navbar from './components/Navbar'
import Footer from './components/Footer'
import HomePage from './pages/HomePage'
import DiagnosePage from './pages/DiagnosePage'
import ResolutionsPage from './pages/ResolutionsPage'
import AboutPage from './pages/AboutPage'
import NotFoundPage from './pages/NotFoundPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import AccountPage from './pages/AccountPage'
import RequestPage from './pages/RequestPage'
import TechniciansPage from './pages/TechniciansPage'
import BookPage from './pages/BookPage'
import BookingsPage from './pages/BookingsPage'
import BookingDetailPage from './pages/BookingDetailPage'
import TechnicianProfilePage from './pages/TechnicianProfilePage'
import AdminPage from './pages/AdminPage'
import GuidesPage from './pages/GuidesPage'
import { useRouter } from './lib/router'
import { ROUTES } from './data/content'

// App = the overall page frame. It picks which screen to show based on the URL.
function CurrentPage({ pathname, search }: { pathname: string; search: string }) {
  // Treat "/about/" the same as "/about"
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  if (path.startsWith(ROUTES.requestPrefix)) {
    let id = ''
    try {
      id = decodeURIComponent(path.slice(ROUTES.requestPrefix.length))
    } catch {
      return <NotFoundPage /> // malformed link, e.g. a stray "%"
    }
    // key: a different request ID gives a fresh page (no leftover state)
    return id && !id.includes('/') ? <RequestPage key={id} requestId={id} /> : <NotFoundPage />
  }
  if (path.startsWith(ROUTES.bookingPrefix)) {
    let id = ''
    try {
      id = decodeURIComponent(path.slice(ROUTES.bookingPrefix.length))
    } catch {
      return <NotFoundPage />
    }
    return id && !id.includes('/') ? <BookingDetailPage key={id} bookingId={id} /> : <NotFoundPage />
  }
  switch (path) {
    case ROUTES.home:
      return <HomePage />
    case ROUTES.diagnose:
      return <DiagnosePage />
    case ROUTES.resolutions:
      return <ResolutionsPage />
    case ROUTES.about:
      return <AboutPage />
    case ROUTES.login:
      return <LoginPage />
    case ROUTES.register:
      return <RegisterPage />
    case ROUTES.account:
      return <AccountPage />
    case ROUTES.technicians:
      return <TechniciansPage key={search} />
    case ROUTES.book:
      return <BookPage key={search} />
    case ROUTES.bookings:
      return <BookingsPage />
    case ROUTES.technicianProfile:
      return <TechnicianProfilePage />
    case ROUTES.admin:
      return <AdminPage />
    case ROUTES.guides:
      return <GuidesPage />
    default:
      return <NotFoundPage />
  }
}

export default function App() {
  const { location } = useRouter()

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-navy-900 px-4 py-2 text-sm font-semibold text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <Navbar />
      <main id="main" className="flex-1 bg-canvas">
        <CurrentPage pathname={location.pathname} search={location.search} />
      </main>
      <Footer />
    </div>
  )
}
