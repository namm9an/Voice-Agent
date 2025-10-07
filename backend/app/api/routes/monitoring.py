"""
Monitoring endpoints - Health checks and metrics
"""
from fastapi import APIRouter, HTTPException
from typing import Dict
import logging

from app.services.health_monitor import get_health_monitor, ServiceState
from app.services.metrics_manager import get_metrics_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/health")
async def health_check() -> Dict:
    """
    Health check endpoint for load balancers and orchestration
    """
    try:
        health_monitor = get_health_monitor()
        all_health = health_monitor.get_all_health()

        # Check if any critical service is down
        critical_services = ["asr_primary", "llm_primary", "tts_primary"]
        critical_down = [
            name for name in critical_services
            if name in all_health and all_health[name]["state"] == "failed"
        ]

        # Determine overall health
        if critical_down:
            status = "unhealthy"
            http_code = 503
        elif any(h["state"] == "degraded" for h in all_health.values()):
            status = "degraded"
            http_code = 200
        else:
            status = "healthy"
            http_code = 200

        response = {
            "status": status,
            "services": all_health,
            "critical_down": critical_down
        }

        if http_code == 503:
            raise HTTPException(status_code=http_code, detail=response)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[HEALTH] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/services")
async def service_health() -> Dict:
    """
    Detailed health status for all services
    """
    try:
        health_monitor = get_health_monitor()
        return health_monitor.get_all_health()
    except Exception as e:
        logger.error(f"[HEALTH-SERVICES] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_metrics() -> Dict:
    """
    Prometheus-compatible metrics endpoint
    """
    try:
        metrics_manager = get_metrics_manager()
        aggregate = metrics_manager.get_aggregate_metrics()

        # Format for Prometheus (or return JSON)
        return {
            "active_sessions": aggregate["active_sessions"],
            "total_sessions": aggregate["total_sessions"],
            "total_errors": aggregate["total_errors"],
            "total_barge_ins": aggregate["total_barge_ins"],
            "avg_latencies_ms": aggregate["avg_latencies_ms"],
            "latency_targets": aggregate["latency_targets"]
        }
    except Exception as e:
        logger.error(f"[METRICS] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/sessions")
async def get_session_metrics() -> Dict:
    """
    Get metrics for active sessions
    """
    try:
        metrics_manager = get_metrics_manager()
        return {
            "active_sessions": list(metrics_manager.active_sessions.keys()),
            "count": len(metrics_manager.active_sessions)
        }
    except Exception as e:
        logger.error(f"[METRICS-SESSIONS] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def system_status() -> Dict:
    """
    Combined system status - health + metrics
    """
    try:
        health_monitor = get_health_monitor()
        metrics_manager = get_metrics_manager()

        return {
            "health": health_monitor.get_all_health(),
            "metrics": metrics_manager.get_aggregate_metrics()
        }
    except Exception as e:
        logger.error(f"[STATUS] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health/reset/{service_id}")
async def reset_service_health(service_id: str) -> Dict:
    """
    Reset health status for a service (admin endpoint)
    """
    try:
        health_monitor = get_health_monitor()
        service = health_monitor.get_service_health(service_id)

        if not service:
            raise HTTPException(status_code=404, detail=f"Service {service_id} not found")

        # Reset failure count
        service.failure_count = 0
        service.state = ServiceState.HEALTHY
        service.last_error = None

        logger.info(f"[HEALTH-RESET] Reset health for {service_id}")

        return {
            "service_id": service_id,
            "status": "reset",
            "health": service.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[HEALTH-RESET] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
