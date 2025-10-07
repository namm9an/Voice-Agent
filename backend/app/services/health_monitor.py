"""
Health Monitor - Checks GPU node health and implements circuit breaker pattern
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
import aiohttp

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """Circuit breaker states"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class ServiceHealth:
    """Health status for a service"""
    name: str
    url: str
    state: ServiceState = ServiceState.HEALTHY
    failure_count: int = 0
    last_check: float = 0.0
    last_success: float = 0.0
    last_error: Optional[str] = None
    latency_ms: float = 0.0

    def is_healthy(self) -> bool:
        """Check if service is healthy"""
        return self.state == ServiceState.HEALTHY

    def record_success(self, latency_ms: float):
        """Record successful health check"""
        self.state = ServiceState.HEALTHY
        self.failure_count = 0
        self.last_success = time.time()
        self.latency_ms = latency_ms
        self.last_error = None

    def record_failure(self, error: str):
        """Record failed health check"""
        self.failure_count += 1
        self.last_error = error

        if self.failure_count >= 3:
            self.state = ServiceState.FAILED
            logger.error(f"[HEALTH] {self.name} marked as FAILED after {self.failure_count} failures")
        elif self.failure_count >= 2:
            self.state = ServiceState.DEGRADED
            logger.warning(f"[HEALTH] {self.name} marked as DEGRADED ({self.failure_count} failures)")

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "url": self.url,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_check": self.last_check,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "latency_ms": round(self.latency_ms, 2)
        }


class HealthMonitor:
    """Monitors service health and manages failover"""

    def __init__(self, check_interval: int = 30, timeout: int = 3):
        self.settings = get_settings()
        self.check_interval = check_interval
        self.timeout = timeout

        # Service health tracking
        self.services: Dict[str, ServiceHealth] = {}

        # HTTP session
        self.http_session: Optional[aiohttp.ClientSession] = None

        # Background task
        self.monitor_task: Optional[asyncio.Task] = None
        self.running = False

        logger.info(f"[HEALTH-MONITOR] Initialized (interval={check_interval}s, timeout={timeout}s)")

    async def start(self):
        """Start health monitoring"""
        # Initialize HTTP session
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=2)
        self.http_session = aiohttp.ClientSession(timeout=timeout)

        # Initialize service tracking
        self._initialize_services()

        # Start monitoring task
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("[HEALTH-MONITOR] Started")

    async def stop(self):
        """Stop health monitoring"""
        self.running = False

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        if self.http_session and not self.http_session.closed:
            await self.http_session.close()

        logger.info("[HEALTH-MONITOR] Stopped")

    def _initialize_services(self):
        """Initialize service health tracking"""
        # ASR (Whisper)
        if self.settings.whisper_base_url:
            self.services["asr_primary"] = ServiceHealth(
                name="ASR (Whisper)",
                url=self.settings.whisper_base_url
            )

        # LLM (Phi-3.5)
        if self.settings.llm_base_url:
            self.services["llm_primary"] = ServiceHealth(
                name="LLM (Phi-3.5)",
                url=self.settings.llm_base_url
            )

        # TTS (Parler)
        if self.settings.parler_tts_base_url:
            self.services["tts_primary"] = ServiceHealth(
                name="TTS (Parler)",
                url=self.settings.parler_tts_base_url
            )

        # TTS Fallback (XTTS)
        if self.settings.xtts_tts_base_url:
            self.services["tts_fallback"] = ServiceHealth(
                name="TTS (XTTS)",
                url=self.settings.xtts_tts_base_url
            )

        logger.info(f"[HEALTH-MONITOR] Tracking {len(self.services)} services")

    async def _monitor_loop(self):
        """Background monitoring loop"""
        try:
            while self.running:
                # Check all services
                await self._check_all_services()

                # Wait for next interval
                await asyncio.sleep(self.check_interval)

        except asyncio.CancelledError:
            logger.info("[HEALTH-MONITOR] Monitor loop cancelled")
        except Exception as e:
            logger.error(f"[HEALTH-MONITOR] Monitor loop error: {e}", exc_info=True)

    async def _check_all_services(self):
        """Check health of all services"""
        tasks = [
            self._check_service(service_id, health)
            for service_id, health in self.services.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_service(self, service_id: str, health: ServiceHealth):
        """Check health of a single service"""
        health.last_check = time.time()

        try:
            start_time = time.perf_counter()

            # Try health endpoint first, fall back to base URL
            check_url = f"{health.url.rstrip('/')}/health"

            async with self.http_session.get(check_url) as response:
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status == 200:
                    health.record_success(latency_ms)
                    logger.debug(f"[HEALTH-CHECK] {health.name} OK ({latency_ms:.0f}ms)")
                else:
                    health.record_failure(f"HTTP {response.status}")
                    logger.warning(f"[HEALTH-CHECK] {health.name} returned {response.status}")

        except asyncio.TimeoutError:
            health.record_failure("Timeout")
            logger.warning(f"[HEALTH-CHECK] {health.name} timeout")
        except aiohttp.ClientError as e:
            health.record_failure(str(e))
            logger.warning(f"[HEALTH-CHECK] {health.name} error: {e}")
        except Exception as e:
            health.record_failure(str(e))
            logger.error(f"[HEALTH-CHECK] {health.name} unexpected error: {e}")

    def get_service_health(self, service_id: str) -> Optional[ServiceHealth]:
        """Get health status for a service"""
        return self.services.get(service_id)

    def is_service_healthy(self, service_id: str) -> bool:
        """Check if a service is healthy"""
        health = self.services.get(service_id)
        return health.is_healthy() if health else False

    def get_all_health(self) -> Dict:
        """Get health status for all services"""
        return {
            service_id: health.to_dict()
            for service_id, health in self.services.items()
        }

    def get_best_service(self, service_type: str) -> Optional[str]:
        """Get best available service of a type (primary or fallback)"""
        # Try primary first
        primary_id = f"{service_type}_primary"
        if primary_id in self.services and self.services[primary_id].is_healthy():
            return primary_id

        # Try fallback
        fallback_id = f"{service_type}_fallback"
        if fallback_id in self.services and self.services[fallback_id].is_healthy():
            logger.warning(f"[HEALTH-FAILOVER] Using fallback for {service_type}")
            return fallback_id

        # No healthy service available
        logger.error(f"[HEALTH-CRITICAL] No healthy {service_type} service available")
        return None


# Global health monitor instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get or create global health monitor"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
