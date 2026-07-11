import json
from datetime import datetime
from json import JSONDecodeError
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# Change these constants to your location.
CITY_NAME = "Weitenung"
COUNTRY_CODE = "DE"

# Optional solar panel estimate settings.
PANEL_LENGTH_M = 1.72
PANEL_WIDTH_M = 1.13
PANEL_AREA_M2 = PANEL_LENGTH_M * PANEL_WIDTH_M
PANEL_RATED_POWER_W = 400
PANEL_EFFICIENCY = PANEL_RATED_POWER_W / (1000 * PANEL_AREA_M2)
PANEL_COUNT = 2
SYSTEM_AC_EFFICIENCY = 0.95
PANEL_TILT_DEG = 26.5
PANEL_AZIMUTH_DEG = 35 #https://azimut.polka-umwelt.de/


def fetch_json(url: str) -> dict:
	request = Request(url, headers={"User-Agent": "hello-weather-script/1.0"})
	with urlopen(request, timeout=10) as response:
		payload = response.read().decode("utf-8", errors="replace")

	try:
		return json.loads(payload)
	except JSONDecodeError as exc:
		preview = payload[:120].strip() or "<empty response>"
		raise ValueError(f"Invalid JSON from API: {preview}") from exc


def resolve_location() -> dict:
	city = CITY_NAME.strip()
	if not city:
		raise ValueError("CITY_NAME is empty. Set CITY_NAME to a city, e.g. 'Karlsruhe'.")

	url = (
		"https://geocoding-api.open-meteo.com/v1/search"
		f"?name={quote(city)}&count=1&language=en&format=json"
	)

	country = COUNTRY_CODE.strip()
	if country:
		url += f"&countryCode={quote(country)}"

	data = fetch_json(url)
	results = data.get("results") or []
	if not results:
		raise ValueError(f"No location found for city '{city}'.")

	place = results[0]
	return {
		"name": place.get("name", city),
		"country": place.get("country", "Unknown"),
		"latitude": float(place["latitude"]),
		"longitude": float(place["longitude"]),
		"timezone": place.get("timezone", "UTC"),
	}


def weather_code_to_text(code: int) -> str:
	weather_codes = {
		0: "Clear sky",
		1: "Mainly clear",
		2: "Partly cloudy",
		3: "Overcast",
		45: "Fog",
		48: "Rime fog",
		51: "Light drizzle",
		53: "Moderate drizzle",
		55: "Dense drizzle",
		56: "Light freezing drizzle",
		57: "Dense freezing drizzle",
		61: "Slight rain",
		63: "Moderate rain",
		65: "Heavy rain",
		66: "Light freezing rain",
		67: "Heavy freezing rain",
		71: "Slight snow",
		73: "Moderate snow",
		75: "Heavy snow",
		77: "Snow grains",
		80: "Slight rain showers",
		81: "Moderate rain showers",
		82: "Violent rain showers",
		85: "Slight snow showers",
		86: "Heavy snow showers",
		95: "Thunderstorm",
		96: "Thunderstorm with slight hail",
		99: "Thunderstorm with heavy hail",
	}
	return weather_codes.get(code, f"Unknown weather code {code}")


def estimate_panel_output_w(irradiance_w_m2: float) -> float:
	return irradiance_w_m2 * PANEL_AREA_M2 * PANEL_EFFICIENCY


def estimate_array_output_w(panel_output_w: float) -> float:
	return panel_output_w * PANEL_COUNT


def estimate_ac_output_w(array_output_w: float) -> float:
	return array_output_w * SYSTEM_AC_EFFICIENCY


def get_weather(location: dict) -> str:
	lat = location["latitude"]
	lon = location["longitude"]
	tz = quote(location["timezone"])
	url = (
		"https://api.open-meteo.com/v1/forecast"
		f"?latitude={lat}&longitude={lon}"
		"&current=temperature_2m,relative_humidity_2m,weather_code,global_tilted_irradiance,shortwave_radiation"
		f"&tilt={PANEL_TILT_DEG}&azimuth={PANEL_AZIMUTH_DEG}"
		f"&timezone={tz}"
	)
	data = fetch_json(url)

	current = data["current"]
	temp_c = current.get("temperature_2m", "?")
	humidity = current.get("relative_humidity_2m", "?")
	tilted_irradiance_raw = current.get("global_tilted_irradiance")
	horizontal_irradiance_raw = current.get("shortwave_radiation")
	raw_code = current.get("weather_code", -1)
	try:
		code = int(raw_code)
	except (TypeError, ValueError):
		code = -1
	desc = weather_code_to_text(code)

	try:
		tilted_irradiance = float(tilted_irradiance_raw)
		horizontal_irradiance = float(horizontal_irradiance_raw)
		panel_output_w = estimate_panel_output_w(tilted_irradiance)
		array_output_w = estimate_array_output_w(panel_output_w)
		ac_output_w = estimate_ac_output_w(array_output_w)
		density_w_m2 = tilted_irradiance * PANEL_EFFICIENCY
		solar_text = (
			f"tilted solar {tilted_irradiance:.0f} W/m^2, horizontal {horizontal_irradiance:.0f} W/m^2, "
			f"panel {density_w_m2:.0f} W/m^2, "
			f"panel DC {panel_output_w:.0f} W, array DC {array_output_w:.0f} W, "
			f"AC {ac_output_w:.0f} W, tilt {PANEL_TILT_DEG}°, azimuth {PANEL_AZIMUTH_DEG}°"
		)
	except (TypeError, ValueError):
		solar_text = "solar data unavailable"

	name = location.get("name", CITY_NAME)
	country = location.get("country", "Unknown")
	return f"{name}, {country}: {temp_c}°C, {desc}, humidity {humidity}%, {solar_text}"


def get_time(timezone_name: str) -> str:
	try:
		now = datetime.now(ZoneInfo(timezone_name))
	except ZoneInfoNotFoundError:
		now = datetime.utcnow()
		return f"{now.isoformat(timespec='seconds')} (UTC, invalid timezone '{timezone_name}')"

	return f"{now.isoformat(timespec='seconds')} ({timezone_name})"


def main() -> None:
	try:
		location = resolve_location()
		weather = get_weather(location)
		current_time = get_time(location["timezone"])
	except (URLError, TimeoutError, KeyError, ValueError) as exc:
		print(f"Could not fetch live weather/time data: {exc}")
		return

	print("Current weather:")
	print(weather)
	print()
	print("Current time:")
	print(current_time)
  
if __name__ == "__main__":
	main()
