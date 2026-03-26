# frontend/services/mock_backend.py

import asyncio

async def get_workflow_mock(query: str):
    await asyncio.sleep(1)  # simulate latency

    return {
        "nodes": [
            {"name": "QueryAnalyzer", "type": "agent"},
            {"name": "ReportGenerator", "type": "agent"}
        ],
        "connections": {
            "QueryAnalyzer": ["ReportGenerator"]
        }
    }


async def run_workflow_mock(query: str, workflow: dict):
    steps = [
        {
            "type": "workflow_updated",
            "workflow": {
                "nodes": [
                    {"name": "QueryAnalyzer", "type": "agent"},
                    {"name": "ProductSearch_1", "type": "api"},
                    {"name": "ProductSearch_2", "type": "api"},
                    {"name": "ReviewAnalyzer", "type": "rag"},
                    {"name": "ReportGenerator", "type": "agent"}
                ],
                "connections": {
                    "QueryAnalyzer": ["ProductSearch_1", "ProductSearch_2"],
                    "ProductSearch_1": ["ReviewAnalyzer"],
                    "ProductSearch_2": ["ReviewAnalyzer"],
                    "ReviewAnalyzer": ["ReportGenerator"]
                }
            }
        },
        {"type": "node_started", "node_name": "QueryAnalyzer"},
        {"type": "node_completed", "node_name": "QueryAnalyzer"},
        {"type": "node_started", "node_name": "ProductSearch_1"},
        {"type": "node_completed", "node_name": "ProductSearch_1"},
        {"type": "node_started", "node_name": "ProductSearch_2"},
        {"type": "node_completed", "node_name": "ProductSearch_2"},
        {"type": "node_started", "node_name": "ReviewAnalyzer"},
        {"type": "node_completed", "node_name": "ReviewAnalyzer"},
        {"type": "node_started", "node_name": "ReportGenerator"},
        {"type": "node_completed", "node_name": "ReportGenerator"},
        {
            "type": "final",
            "html": "<h1>Top Product</h1><p>Wireless Earbuds - $79</p>"
        }
    ]

    for step in steps:
        await asyncio.sleep(0.8)
        yield step
