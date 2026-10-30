"""All HTTP routes, gathered under the /api prefix."""

from fastapi import APIRouter

from .routes import admin, auth, bookings, cases, health, knowledge, notifications, payments, photos, repair_requests, safety, technician, technicians, trades

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(trades.router)
api_router.include_router(safety.router)
api_router.include_router(auth.router)
api_router.include_router(repair_requests.router)
api_router.include_router(technicians.router)
api_router.include_router(technician.router)
api_router.include_router(bookings.router)
api_router.include_router(notifications.router)
api_router.include_router(payments.router)
api_router.include_router(photos.router)
api_router.include_router(knowledge.router)
api_router.include_router(admin.router)
api_router.include_router(cases.router)
