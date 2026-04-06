"""OpenTelemetry 追蹤設定。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_tracer_provider = None


def setup_tracing(otlp_endpoint: str, service_name: str = "taigi-flow") -> None:
    """初始化 OpenTelemetry tracer，匯出至 OTLP collector。

    若 OTLP endpoint 無法連線，自動 fallback 為 no-op（不影響主流程）。
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        logger.info("OpenTelemetry tracing enabled (endpoint=%s)", otlp_endpoint)

    except Exception as exc:
        logger.warning("OpenTelemetry setup failed, tracing disabled: %s", exc)


def get_tracer(name: str = "taigi_flow"):
    """取得 tracer 實例。"""
    from opentelemetry import trace

    return trace.get_tracer(name)


def shutdown_tracing() -> None:
    global _tracer_provider
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception:
            pass
        _tracer_provider = None
