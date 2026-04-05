"""Shared cached data provider instance.

Import ``provider`` from this module instead of instantiating
YahooFinanceProvider directly — this ensures a single cache is
shared across all API routes.
"""

from data.cache import CachedDataProvider
from data.yahoo_provider import YahooFinanceProvider

provider = CachedDataProvider(YahooFinanceProvider())
