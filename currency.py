"""
Currency conversion module using ECB exchange rates.
Fetches daily rates from the European Central Bank for EUR conversion.
"""

import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Tuple
import requests

# ECB daily exchange rates XML feed
ECB_DAILY_URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'

# Cache for exchange rates (currency -> rate)
_rates_cache: dict = {}
_cache_date: Optional[date] = None


def fetch_ecb_rates() -> dict:
    """
    Fetch current exchange rates from ECB.

    Returns:
        dict mapping currency codes to exchange rates (1 EUR = X currency)
    """
    global _rates_cache, _cache_date

    # Return cached rates if fetched today
    today = date.today()
    if _cache_date == today and _rates_cache:
        return _rates_cache

    try:
        response = requests.get(ECB_DAILY_URL, timeout=10)
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.content)

        # ECB XML namespace
        namespaces = {
            'gesmes': 'http://www.gesmes.org/xml/2002-08-01',
            'eurofxref': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'
        }

        rates = {'EUR': Decimal('1.0')}  # EUR to EUR is always 1

        # Find the Cube element containing rates
        cube = root.find('.//eurofxref:Cube/eurofxref:Cube', namespaces)
        if cube is not None:
            for rate_elem in cube.findall('eurofxref:Cube', namespaces):
                currency = rate_elem.get('currency')
                rate = rate_elem.get('rate')
                if currency and rate:
                    rates[currency] = Decimal(rate)

        # Update cache
        _rates_cache = rates
        _cache_date = today

        return rates

    except Exception as e:
        # If fetch fails and we have cached rates, use them
        if _rates_cache:
            return _rates_cache
        raise RuntimeError(f'Failed to fetch ECB rates: {e}')


def get_exchange_rate(currency: str) -> Optional[Decimal]:
    """
    Get the exchange rate for a currency (1 EUR = X currency).

    Args:
        currency: 3-letter currency code (e.g., 'USD', 'GBP')

    Returns:
        Exchange rate as Decimal, or None if currency not supported
    """
    currency = currency.upper()

    if currency == 'EUR':
        return Decimal('1.0')

    rates = fetch_ecb_rates()
    return rates.get(currency)


def convert_to_eur(amount: Decimal, currency: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Convert an amount to EUR using ECB exchange rates.

    Args:
        amount: Amount in original currency
        currency: 3-letter currency code

    Returns:
        Tuple of (amount_eur, exchange_rate) or (None, None) if conversion failed
    """
    currency = currency.upper()

    if currency == 'EUR':
        return (amount, Decimal('1.0'))

    rate = get_exchange_rate(currency)
    if rate is None:
        return (None, None)

    # ECB rates are "1 EUR = X currency", so divide to get EUR
    amount_eur = amount / rate

    # Round to 2 decimal places
    amount_eur = amount_eur.quantize(Decimal('0.01'))

    return (amount_eur, rate)


def get_supported_currencies() -> list:
    """
    Get list of currencies supported by ECB.

    Returns:
        List of 3-letter currency codes
    """
    rates = fetch_ecb_rates()
    return sorted(rates.keys())
