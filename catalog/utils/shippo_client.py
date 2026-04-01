"""
Shippo v3 shipping label generation utility.
Requires SHIPPO_API_KEY in settings.
"""
from django.conf import settings


def generate_shipping_label(
    from_name: str, from_street: str, from_city: str, from_zip: str, from_country: str,
    to_name: str, to_street: str, to_city: str, to_zip: str, to_country: str,
) -> dict:
    """
    Create a Shippo shipment and purchase the cheapest available label.

    Returns dict:
        label_url (str), tracking_number (str), shipping_cost_usd (float)

    Raises ValueError if API key is missing or label purchase fails.
    """
    api_key = getattr(settings, 'SHIPPO_API_KEY', '')
    if not api_key:
        raise ValueError("SHIPPO_API_KEY is not configured in settings.")

    import shippo
    from shippo.models import components

    s = shippo.Shippo(api_key_header=api_key)

    shipment = s.shipments.create(
        request=components.ShipmentCreateRequest(
            address_from=components.AddressCreateRequest(
                name=from_name,
                street1=from_street,
                city=from_city,
                zip=from_zip,
                country=from_country,
            ),
            address_to=components.AddressCreateRequest(
                name=to_name,
                street1=to_street,
                city=to_city,
                zip=to_zip,
                country=to_country,
            ),
            parcels=[components.ParcelCreateRequest(
                length='10',
                width='8',
                height='3',
                distance_unit=components.DistanceUnitEnum.IN,
                weight='1',
                mass_unit=components.WeightUnitEnum.LB,
            )],
            async_=False,
        )
    )

    if not shipment.rates:
        raise ValueError("No shipping rates returned for this route.")

    cheapest = sorted(shipment.rates, key=lambda r: float(r.amount))[0]

    transaction = s.transactions.create(
        request=components.TransactionCreateRequest(
            rate=cheapest.object_id,
            label_file_type=components.LabelFileTypeEnum.PDF,
            async_=False,
        )
    )

    if transaction.status != 'SUCCESS':
        msgs = getattr(transaction, 'messages', '')
        raise ValueError(f"Label purchase failed: {msgs}")

    return {
        'label_url': transaction.label_url,
        'tracking_number': transaction.tracking_number,
        'shipping_cost_usd': float(cheapest.amount),
    }
