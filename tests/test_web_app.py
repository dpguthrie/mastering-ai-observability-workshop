from __future__ import annotations

from starlette.testclient import TestClient

from aiewf_support.web.app import app


def test_config_endpoint_exposes_chat_models() -> None:
    client = TestClient(app)

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert data["default_model"]
    assert data["customer_id"].startswith("cus_")
    assert {model["id"] for model in data["models"]} >= {data["default_model"]}
    assert all("tools" not in model and "vision" not in model for model in data["models"])


def test_homepage_serves_local_chat_ui() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Trailhead Support Agent" in response.text
    assert "/static/app.js" in response.text
    assert "customerSelect" in response.text
    assert "Attach context" not in response.text
    assert "artifact" not in response.text


def test_products_endpoint_uses_support_tools() -> None:
    client = TestClient(app)

    response = client.get("/api/products")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert any(product["product_id"] == "prod_2001" for product in data["products"])


def test_customers_endpoint_supports_demo_picker() -> None:
    client = TestClient(app)

    response = client.get("/api/customers")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert any(customer["customer_id"] == "cus_1002" for customer in data["customers"])


def test_chat_endpoint_uses_streaming_trace_id(monkeypatch) -> None:
    from agents import Runner

    captured_kwargs = []

    class FakeTrace:
        trace_id = "trace_test"

    class FakeResult:
        trace = FakeTrace()
        final_output = "Your order is on the way."

        async def stream_events(self):
            if False:
                yield None

    def fake_run_streamed(cls: object, *args, **kwargs) -> FakeResult:
        captured_kwargs.append(kwargs)
        return FakeResult()

    monkeypatch.setattr(Runner, "run_streamed", classmethod(fake_run_streamed))
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Where is my order?"}],
            "model": "gpt-test",
            "customer_id": "cus_1002",
            "conversation_id": "chat_test",
        },
    )

    assert response.status_code == 200
    assert '"request_id": "trace_test"' in response.text
    assert '"conversation_id": "chat_test"' in response.text
    assert "Your order is on the way." in response.text
    run_config = captured_kwargs[0]["run_config"]
    assert run_config.trace_metadata["conversation_id"] == "chat_test"
    assert run_config.trace_metadata["surface"] == "chat_ui"
    assert run_config.trace_metadata["customer_id"] == "cus_1002"
    assert set(run_config.trace_metadata) == {"conversation_id", "surface", "customer_id", "turn_count"}


def test_chat_endpoint_streams_tool_activity(monkeypatch) -> None:
    from agents import Runner

    class FakeTrace:
        trace_id = "trace_tool_test"

    class FakeToolCallRawItem:
        name = "search_customer_orders"
        call_id = "call_orders"

    class FakeToolOutputRawItem:
        call_id = "call_orders"

    class FakeToolCallItem:
        raw_item = FakeToolCallRawItem()

    class FakeToolOutputItem:
        raw_item = FakeToolOutputRawItem()

    class FakeStreamEvent:
        type = "run_item_stream_event"

        def __init__(self, name: str, item: object) -> None:
            self.name = name
            self.item = item

    class FakeResult:
        trace = FakeTrace()
        final_output = "I found your latest order."

        async def stream_events(self):
            yield FakeStreamEvent("tool_called", FakeToolCallItem())
            yield FakeStreamEvent("tool_output", FakeToolOutputItem())

    def fake_run_streamed(cls: object, *args, **kwargs) -> FakeResult:
        return FakeResult()

    monkeypatch.setattr(Runner, "run_streamed", classmethod(fake_run_streamed))
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Where is my latest order?"}],
            "model": "gpt-test",
            "customer_id": "cus_1002",
        },
    )

    assert response.status_code == 200
    assert "event: activity" in response.text
    assert '"tool": "search_customer_orders"' in response.text
    assert "Searching customer orders" in response.text
    assert "Searched customer orders" in response.text
    assert "I found your latest order." in response.text

