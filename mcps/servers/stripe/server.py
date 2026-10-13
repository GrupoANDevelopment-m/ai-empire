"""Stripe MCP server — provides Stripe payment tools.

Wraps the official stripe-python library to expose:
- create_customer
- create_subscription
- list_invoices
- create_payment_intent
- get_balance
"""
import os
import stripe
from typing import Any, Optional

stripe.api_key = os.getenv("STRIPE_API_KEY", "")


def list_tools() -> list[dict]:
    return [
        {
            "name": "stripe_create_customer",
            "description": "Create a new Stripe customer",
            "input_schema": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "name": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "required": ["email"],
            },
        },
        {
            "name": "stripe_create_subscription",
            "description": "Create a subscription for a customer",
            "input_schema": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "price_id": {"type": "string"},
                    "trial_days": {"type": "integer"},
                },
                "required": ["customer_id", "price_id"],
            },
        },
        {
            "name": "stripe_list_invoices",
            "description": "List invoices for a customer",
            "input_schema": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["customer_id"],
            },
        },
        {
            "name": "stripe_create_payment_intent",
            "description": "Create a payment intent",
            "input_schema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer"},
                    "currency": {"type": "string"},
                    "customer_id": {"type": "string"},
                },
                "required": ["amount", "currency"],
            },
        },
        {
            "name": "stripe_get_balance",
            "description": "Get account balance",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]


async def call_tool(name: str, arguments: dict) -> Any:
    if name == "stripe_create_customer":
        return stripe.Customer.create(**arguments)
    if name == "stripe_create_subscription":
        return stripe.Subscription.create(**arguments)
    if name == "stripe_list_invoices":
        return stripe.Invoice.list(customer=arguments["customer_id"], limit=arguments.get("limit", 10))
    if name == "stripe_create_payment_intent":
        return stripe.PaymentIntent.create(**arguments)
    if name == "stripe_get_balance":
        return stripe.Balance.retrieve()
    raise ValueError(f"Unknown tool: {name}")
