import datetime as dt

from app.collectors import brittany, dfds

D = dt.date(2026, 12, 5)

DFDS_NEW = """Route options
00:35
Dover
03:15
Calais
Duration: 1h40min
from
£103.00
Select ticket type
05:45
Dover
09:15
Dunkirk
Duration: 2h30min
from
£99.00
22:00
Dover
00:30
Dunkirk
Duration: 2h30min
from
£96.00
"""

DFDS_OLD = """Fares
17:00 - Newhaven - Dieppe
£73.50

"""


def test_dfds_new_site_prices_both_dover_routes():
    qs = {q.route_id: q for q in dfds._parse(DFDS_NEW, "dfds-dover-calais", D)}
    assert qs["dfds-dover-calais"].price == 103.0 and qs["dfds-dover-calais"].departure == "00:35"
    assert qs["dfds-dover-dunkirk"].price == 96.0 and qs["dfds-dover-dunkirk"].departure == "22:00"


def test_dfds_legacy_site():
    (q,) = dfds._parse(DFDS_OLD, "dfds-newhaven-dieppe", D)
    assert q.route_id == "dfds-newhaven-dieppe" and q.price == 73.5


def _bf(time, std, mandatory=False, cabin=0, full=False):
    return {"crossingPrices": {
        "departureDateTime": {"time": time}, "standardPrice": {"amount": std} if std else None,
        "full": full, "isAccommodationMandatory": mandatory,
        "cabinsIncluded": [{"quantity": 1, "price": {"amount": cabin}}] if cabin else []}}


def test_brittany_adds_compulsory_cabin_and_skips_full():
    data = {"currency": "GBP", "crossings": [{"date": "2026-12-05", "prices": [
        _bf("08:00", 153), _bf("15:00", 134), _bf("23:00", 100, mandatory=True, cabin=64),
        _bf("10:00", 50, full=True), _bf("11:00", None)]}]}
    (q,) = brittany.parse("bf-portsmouth-caen", data)
    assert q.price == 134 and q.departure == "15:00"
    data["crossings"][0]["prices"] = [_bf("23:30", 158, mandatory=True, cabin=102)]
    (q,) = brittany.parse("bf-portsmouth-santander", data)
    assert q.price == 260 and "cabin" in q.detail
