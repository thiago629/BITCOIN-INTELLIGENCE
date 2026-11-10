"""Builds the configured provider chain."""

import httpx

from app.core.config import Settings
from app.providers.base import BlockchainProvider
from app.providers.esplora import EsploraProvider
from app.providers.http import ProviderHttpClient
from app.providers.mempool_space import MempoolSpaceProvider


def build_providers(settings: Settings, client: httpx.AsyncClient) -> list[BlockchainProvider]:
    providers: list[BlockchainProvider] = []
    for key in settings.providers:
        if key == "mempool":
            http = ProviderHttpClient(
                client, "mempool", settings.mempool_base_url, settings.http_max_retries
            )
            providers.append(MempoolSpaceProvider(http, "mempool", "mempool.space"))
        elif key == "blockstream":
            http = ProviderHttpClient(
                client, "blockstream", settings.blockstream_base_url, settings.http_max_retries
            )
            providers.append(EsploraProvider(http, "blockstream", "blockstream.info"))
        else:
            raise ValueError(f"Unknown data provider '{key}'. Valid: mempool, blockstream")
    if not providers:
        raise ValueError("At least one data provider must be configured (BI_PROVIDERS)")
    return providers
