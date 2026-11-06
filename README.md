# Euro Drive Planner

A student project by Tisloh Makwa, Computer Science with AI student at Nottingham Trent University.

Euro Drive Planner is a local web app I designed and built to find the cheapest way to drive from the UK to mainland Europe. It compares every ferry and Eurotunnel Le Shuttle crossing and adds up fuel, tolls, vignettes and the crossing fare, one way or return. You can find me on [my LinkedIn profile](https://www.linkedin.com/in/tisloh-makwa).

## Why I built it

Planning a drive to Europe means comparing a dozen crossings across several booking sites, then guessing what the drive either side will cost in fuel and tolls. A ferry that looks cheap can lead to a longer, more expensive drive through France. I wanted one tool that prices the whole journey door to door, using live fares where possible rather than guesswork.

## What it does

* Plans door-to-door trips from Great Britain (and Ireland, via the UK) to mainland Europe, comparing every ferry and Le Shuttle crossing, including two-crossing routes.
* Collects **live fares** from Eurotunnel Le Shuttle, DFDS and Brittany Ferries, and falls back to clearly labelled seasonal estimates for other operators.
* Plans **return journeys** as two separate one-way trips, showing a round-trip total and letting you pick the crossing for each direction.
* Costs fuel per country from a **UK MPG slider**, showing petrol and diesel side by side. Tolls come from the distance driven on toll roads, plus fixed tolls such as the Mont Blanc tunnel and Øresund bridge. Vignettes are added for countries such as Austria and Switzerland.
* Ranks routes by cheapest, fastest, or a balance of the two that puts a value on your time.
* Lets you enter a real quote from an operator, which is then used in place of the estimate.
* Shows every option on a map, with an Apple-inspired interface in light and dark mode.

## What I learned and practised

* Designing a route search over a small network: three landmasses (Great Britain, Ireland, mainland Europe) joined by sea crossings, with a cheap screening step and a detailed refinement step.
* Working with OpenStreetMap routing services: OSRM distance tables for screening, and Valhalla routes split by country for fuel, toll-road and motorway distances.
* Point-in-polygon country lookup and polyline decoding in plain Python.
* Building responsible web collectors with Playwright and headless Microsoft Edge. They check robots.txt, refuse non-essential cookies, never log in or bypass bot checks, and save debug screenshots when a site changes.
* Spotting when a booking site's own JSON endpoint is simpler and more robust than driving the page.
* Caching with SQLite (routes for 30 days, fares for 6 hours) so repeat searches return in about a second.
* An async Python API with FastAPI, request validation with Pydantic, and unit tests with pytest.
* A React interface with iOS-style controls (switches, steppers, segmented controls), accessible labelling, light and dark themes, and a layout that adapts to narrow screens.

## Tech stack

Python 3.12, FastAPI, httpx, Playwright (with Microsoft Edge), SQLite, React 18, Vite, Leaflet / react-leaflet, OSRM, Valhalla, Photon (OpenStreetMap geocoding), Natural Earth country borders and ECB exchange rates.

## Run locally

1. Install Python 3.12 and Node.js 20 or later. Microsoft Edge must be installed for the live Le Shuttle and DFDS collectors (it comes with Windows).
2. Create a virtual environment and install the backend:
   `python -m venv .venv` then `.venv\Scripts\python -m pip install -r backend\requirements.txt`
3. Build the frontend: `cd frontend`, `npm install`, `npm run build`.
4. Start the app: `.venv\Scripts\python backend\run.py --port 8000`, or double-click `start.bat`. Then open `http://localhost:8000`.
5. For frontend development, run `npm run dev` in `frontend` (Vite on port 5173, with `/api` proxied to port 8000).
6. Run the tests with `cd backend` then `..\.venv\Scripts\python -m pytest -q tests`.

No API keys or accounts are needed.

## Fare data

| Operator | Source |
|---|---|
| Eurotunnel Le Shuttle (Folkestone → Calais) | **Live.** Runs the public booking flow in headless Edge using a generic "Car" category (no registration plate or make/model) and reads the quote JSON. |
| Le Shuttle (Calais → Folkestone) | Estimate. That flow requires ticking a journey-confirmation box, which the tool deliberately doesn't do. |
| DFDS: Dover ↔ Calais, Dover ↔ Dunkirk, Newhaven ↔ Dieppe | **Live, both directions.** DFDS's search API builds the booking link and the departures page is read. One Dover visit prices both Calais and Dunkirk. |
| DFDS: Newcastle ↔ Amsterdam, Rosslare ↔ Dunkirk | Estimate. The first price shown leaves out the compulsory cabin, so it would look misleadingly cheap. |
| Brittany Ferries: Portsmouth ↔ Caen, Cherbourg, St Malo, Santander, Bilbao; Plymouth ↔ Roscoff, Santander | **Live, both directions,** from the site's own fares JSON with plain HTTP requests (no browser). Compulsory overnight cabins are added. If there's no sailing on your date, the nearest sailing within 3 days is used and noted; routes with none are left out. |
| P&O Ferries | Estimate. The site blocks automated access (HTTP 403). |
| Stena Line | Estimate. robots.txt disallows the booking pages. |
| Irish Ferries | Estimate. |

* Live fares are cached for 6 hours in `backend/var/cache.db`. The first search for a new date takes about 30 seconds; repeat searches take about 1 second.
* Estimated fares are typical one-way prices for a car with 2 adults, by season (low, mid or high). They are adjusted for weekend departures, larger vehicles and extra passengers.
* Most operators' terms don't allow automated price collection, so the collectors are for personal use at a low request rate. Booking sites change, and a collector can break when they do; the app then falls back to estimates and shows a warning.

## How estimates are calculated

* **Fuel:** litres per 100 km = `282.481 ÷ UK MPG` (imperial gallon). Each route is split by country, and litres × that country's petrol or diesel price gives the fuel cost. Both fuels are shown; the one you choose is used in the total.
* **Tolls:** distance on toll roads in each country × that country's per-km rate. Vans, campervans and caravans pay about 1.5×. Fixed tolls such as tunnels and bridges are added when the route passes them.
* **Vignettes:** the cheapest short-term sticker is added once per trip for each country whose motorways the route uses.
* **Time:** driving time + crossing time + check-in. "Balanced" ranks by cost + hours × the value you put on your time.
* **Currency:** prices are converted with daily ECB reference rates (GBP or EUR).
* Fuel prices, toll rates and estimated fares are approximate (as of November 2026) and editable in `backend/app/data/countries.json` and `crossings.json`.
* Estimates cover fuel, tolls, vignettes and crossings only. They don't include accommodation, food, parking, insurance, wear or emissions zones. They are for comparison, not financial advice. Always confirm prices with the operator before booking.

Inputs are range-checked, and searches show loading, empty, warning and error states. Controls are labelled for screen readers, and the layout adapts to narrow screens.
