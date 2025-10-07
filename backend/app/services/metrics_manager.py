"""
Metrics Manager - Fine-grained latency tracking and performance monitoring
"""
import time
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from pathlib import Path
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage"""
    stage_name: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    latency_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def start(self):
        """Mark stage start"""
        self.start_time = time.perf_counter()

    def end(self, success: bool = True, error: Optional[str] = None):
        """Mark stage end and calculate latency"""
        self.end_time = time.perf_counter()
        self.success = success
        self.error = error
        if self.start_time and self.end_time:
            self.latency_ms = (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "stage": self.stage_name,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms else None,
            "success": self.success,
            "error": self.error,
            **self.metadata
        }


@dataclass
class SessionMetricsV2:
    """Enhanced session metrics with fine-grained tracking"""
    session_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    # Stage metrics
    asr_stages: List[StageMetrics] = field(default_factory=list)
    llm_stages: List[StageMetrics] = field(default_factory=list)
    tts_stages: List[StageMetrics] = field(default_factory=list)

    # Aggregate metrics
    total_asr_latency_ms: float = 0.0
    total_llm_latency_ms: float = 0.0
    total_tts_latency_ms: float = 0.0
    pipeline_total_latency_ms: float = 0.0

    # Counts
    asr_chunk_count: int = 0
    llm_token_count: int = 0
    tts_frame_count: int = 0
    barge_in_count: int = 0
    error_count: int = 0

    # End-to-end timing
    e2e_latencies_ms: List[float] = field(default_factory=list)

    def add_asr_stage(self, metadata: Dict = None) -> StageMetrics:
        """Create and track ASR stage"""
        stage = StageMetrics("asr", metadata=metadata or {})
        self.asr_stages.append(stage)
        return stage

    def add_llm_stage(self, metadata: Dict = None) -> StageMetrics:
        """Create and track LLM stage"""
        stage = StageMetrics("llm", metadata=metadata or {})
        self.llm_stages.append(stage)
        return stage

    def add_tts_stage(self, metadata: Dict = None) -> StageMetrics:
        """Create and track TTS stage"""
        stage = StageMetrics("tts", metadata=metadata or {})
        self.tts_stages.append(stage)
        return stage

    def finalize(self):
        """Calculate aggregate metrics"""
        self.end_time = time.time()

        # Aggregate ASR
        self.total_asr_latency_ms = sum(
            s.latency_ms for s in self.asr_stages if s.latency_ms
        )
        self.asr_chunk_count = len(self.asr_stages)

        # Aggregate LLM
        self.total_llm_latency_ms = sum(
            s.latency_ms for s in self.llm_stages if s.latency_ms
        )
        self.llm_token_count = len(self.llm_stages)

        # Aggregate TTS
        self.total_tts_latency_ms = sum(
            s.latency_ms for s in self.tts_stages if s.latency_ms
        )
        self.tts_frame_count = len(self.tts_stages)

        # Pipeline total
        self.pipeline_total_latency_ms = (
            self.total_asr_latency_ms +
            self.total_llm_latency_ms +
            self.total_tts_latency_ms
        )

        # Count errors
        self.error_count = sum(
            1 for stages in [self.asr_stages, self.llm_stages, self.tts_stages]
            for s in stages if not s.success
        )

    def get_summary(self) -> Dict:
        """Get metrics summary"""
        return {
            "session_id": self.session_id,
            "duration_s": round((self.end_time or time.time()) - self.start_time, 2),
            "asr": {
                "chunks": self.asr_chunk_count,
                "total_latency_ms": round(self.total_asr_latency_ms, 2),
                "avg_latency_ms": round(
                    self.total_asr_latency_ms / max(1, self.asr_chunk_count), 2
                )
            },
            "llm": {
                "tokens": self.llm_token_count,
                "total_latency_ms": round(self.total_llm_latency_ms, 2),
                "avg_latency_ms": round(
                    self.total_llm_latency_ms / max(1, self.llm_token_count), 2
                )
            },
            "tts": {
                "frames": self.tts_frame_count,
                "total_latency_ms": round(self.total_tts_latency_ms, 2),
                "avg_latency_ms": round(
                    self.total_tts_latency_ms / max(1, self.tts_frame_count), 2
                )
            },
            "pipeline": {
                "total_latency_ms": round(self.pipeline_total_latency_ms, 2),
            },
            "e2e": {
                "measurements": len(self.e2e_latencies_ms),
                "avg_latency_ms": round(
                    sum(self.e2e_latencies_ms) / max(1, len(self.e2e_latencies_ms)), 2
                ) if self.e2e_latencies_ms else 0,
                "min_latency_ms": round(min(self.e2e_latencies_ms), 2) if self.e2e_latencies_ms else 0,
                "max_latency_ms": round(max(self.e2e_latencies_ms), 2) if self.e2e_latencies_ms else 0,
            },
            "errors": self.error_count,
            "barge_ins": self.barge_in_count
        }


class MetricsManager:
    """Manages metrics collection, aggregation, and persistence"""

    def __init__(self, save_path: Optional[str] = None, window_size: int = 100):
        self.save_path = Path(save_path) if save_path else None
        self.window_size = window_size

        # Active sessions
        self.active_sessions: Dict[str, SessionMetricsV2] = {}

        # Rolling window for aggregates
        self.recent_latencies = {
            "asr": deque(maxlen=window_size),
            "llm": deque(maxlen=window_size),
            "tts": deque(maxlen=window_size),
            "e2e": deque(maxlen=window_size),
            "pipeline": deque(maxlen=window_size)
        }

        # Global counters
        self.total_sessions = 0
        self.total_errors = 0
        self.total_barge_ins = 0

        # Ensure save directory exists
        if self.save_path:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"[METRICS-MANAGER] Initialized (save_path={self.save_path})")

    def create_session(self, session_id: str) -> SessionMetricsV2:
        """Create new session metrics"""
        metrics = SessionMetricsV2(session_id=session_id)
        self.active_sessions[session_id] = metrics
        self.total_sessions += 1
        logger.info(f"[METRICS] Session created: {session_id}")
        return metrics

    def get_session(self, session_id: str) -> Optional[SessionMetricsV2]:
        """Get session metrics"""
        return self.active_sessions.get(session_id)

    def finalize_session(self, session_id: str):
        """Finalize and persist session metrics"""
        metrics = self.active_sessions.get(session_id)
        if not metrics:
            return

        # Calculate aggregates
        metrics.finalize()

        # Update rolling window
        if metrics.asr_chunk_count > 0:
            avg_asr = metrics.total_asr_latency_ms / metrics.asr_chunk_count
            self.recent_latencies["asr"].append(avg_asr)

        if metrics.llm_token_count > 0:
            avg_llm = metrics.total_llm_latency_ms / metrics.llm_token_count
            self.recent_latencies["llm"].append(avg_llm)

        if metrics.tts_frame_count > 0:
            avg_tts = metrics.total_tts_latency_ms / metrics.tts_frame_count
            self.recent_latencies["tts"].append(avg_tts)

        if metrics.e2e_latencies_ms:
            avg_e2e = sum(metrics.e2e_latencies_ms) / len(metrics.e2e_latencies_ms)
            self.recent_latencies["e2e"].append(avg_e2e)

        self.recent_latencies["pipeline"].append(metrics.pipeline_total_latency_ms)

        # Update global counters
        self.total_errors += metrics.error_count
        self.total_barge_ins += metrics.barge_in_count

        # Get summary
        summary = metrics.get_summary()

        # Log summary
        logger.info(
            f"[METRICS-SUMMARY] {session_id} | "
            f"asr={summary['asr']['avg_latency_ms']}ms | "
            f"llm={summary['llm']['avg_latency_ms']}ms | "
            f"tts={summary['tts']['avg_latency_ms']}ms | "
            f"e2e={summary['e2e']['avg_latency_ms']}ms | "
            f"total={summary['pipeline']['total_latency_ms']}ms"
        )

        # Persist to file
        if self.save_path:
            try:
                with open(self.save_path, 'a') as f:
                    json.dump({
                        "timestamp": time.time(),
                        **summary
                    }, f)
                    f.write('\n')
            except Exception as e:
                logger.error(f"[METRICS] Failed to save: {e}")

        # Remove from active
        del self.active_sessions[session_id]

    def get_aggregate_metrics(self) -> Dict:
        """Get current aggregate metrics"""
        def avg(values):
            return round(sum(values) / len(values), 2) if values else 0

        return {
            "active_sessions": len(self.active_sessions),
            "total_sessions": self.total_sessions,
            "total_errors": self.total_errors,
            "total_barge_ins": self.total_barge_ins,
            "avg_latencies_ms": {
                "asr": avg(self.recent_latencies["asr"]),
                "llm": avg(self.recent_latencies["llm"]),
                "tts": avg(self.recent_latencies["tts"]),
                "e2e": avg(self.recent_latencies["e2e"]),
                "pipeline": avg(self.recent_latencies["pipeline"])
            },
            "latency_targets": {
                "asr": {"target_ms": 500, "met": avg(self.recent_latencies["asr"]) < 500},
                "llm": {"target_ms": 300, "met": avg(self.recent_latencies["llm"]) < 300},
                "tts": {"target_ms": 200, "met": avg(self.recent_latencies["tts"]) < 200},
                "e2e": {"target_ms": 1000, "met": avg(self.recent_latencies["e2e"]) < 1000}
            }
        }


# Global metrics manager instance
_metrics_manager: Optional[MetricsManager] = None


def get_metrics_manager(save_path: Optional[str] = None) -> MetricsManager:
    """Get or create global metrics manager"""
    global _metrics_manager
    if _metrics_manager is None:
        _metrics_manager = MetricsManager(save_path=save_path)
    return _metrics_manager
