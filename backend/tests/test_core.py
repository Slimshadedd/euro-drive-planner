import datetime as dt

from app import costs, crossings, geo


def test_country_lookup():
    assert geo.country_at(48.8566, 2.3522) == "FR"
    assert geo.country_at(51.5074, -0.1278) == "GB"
    assert geo.country_at(48.137, 11.575) == "DE"


def test_landmass():
    assert geo.landmass(51.5, -0.12, "GB") == "GB"
    assert geo.landmass(54.6, -5.93, "GB") == "IE"  # Belfast
    assert geo.landmass(53.35, -6.26, "IE") == "IE"
    assert geo.landmass(48.85, 2.35, "FR") == "EU"


def test_polyline_roundtrip_known_value():
    # Google's documented example (precision 5)
    pts = geo.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5)
    assert pts[0] == (38.5, -120.2) and pts[-1] == (43.252, -126.453)


def test_mpg_conversion():
    assert round(costs.Vehicle(mpg=45).l_per_100km, 2) == 6.28


def test_leg_cost_fuel_and_tolls():
    leg = {"countries": {"FR": {"km": 100.0, "toll_km": 80.0, "motorway_km": 80.0, "ferry_km": 0.0}},
           "geometry": [[48.0, 2.0], [48.5, 2.5]]}
    v = costs.Vehicle(mpg=282.481 / 5, fuel="diesel")  # exactly 5 L/100km
    c = costs.leg_cost(leg, v)
    fr = costs.country_data()["countries"]["FR"]
    assert abs(c["fuel_by_type_eur"]["diesel"] - 5 * fr["diesel"]) < 0.01
    assert abs(c["fuel_by_type_eur"]["petrol"] - 5 * fr["petrol"]) < 0.01
    assert abs(c["tolls_eur"] - 80 * fr["toll_per_km"]) < 0.01


def test_vignette_only_when_using_motorways():
    v = costs.Vehicle()
    on = {"countries": {"AT": {"km": 50, "toll_km": 0, "motorway_km": 40, "ferry_km": 0}}, "geometry": []}
    off = {"countries": {"AT": {"km": 50, "toll_km": 0, "motorway_km": 0, "ferry_km": 0}}, "geometry": []}
    assert costs.leg_cost(on, v)["vignettes_eur"] > 0
    assert costs.leg_cost(off, v)["vignettes_eur"] == 0


def test_season_and_fare_estimate():
    r = next(x for x in crossings.routes() if x["id"] == "dfds-dover-calais")
    assert crossings.season(dt.date(2027, 8, 1)) == "high"
    assert crossings.season(dt.date(2027, 2, 10)) == "low"
    low = crossings.estimate_fare_gbp(r, dt.date(2027, 2, 10), crossings.Party())  # Wednesday
    van = crossings.estimate_fare_gbp(r, dt.date(2027, 2, 10), crossings.Party(vehicle="van"))
    assert low == r["fare"]["low"] and van > low


def test_every_route_references_known_ports():
    ports = crossings.ports()
    for r in crossings.routes():
        assert r["from"] in ports and r["to"] in ports
        assert ports[r["from"]]["landmass"] != ports[r["to"]]["landmass"]
