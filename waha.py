"""Compatibility shim for the legacy client name.

The project now uses Meta WhatsApp Cloud API through `meta_client.py`.
This module keeps an import-compatible surface for older code and docs.
"""

from meta_client import MetaClient, get_meta_client


WhatsAppClient = MetaClient


async def get_whatsapp_client() -> MetaClient:
    """Get Meta WhatsApp client (compatibility helper)."""
    return MetaClient()
