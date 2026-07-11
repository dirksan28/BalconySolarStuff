import json
from datetime import datetime
from json import JSONDecodeError
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

##############################################
# Change these constants to your location.
CITY_NAME = "Weitenung" # Name of the city for which to fetch weather and solar data
COUNTRY_CODE = "DE" # Country code for the location

# Solar panel estimate settings. Feel free to change these values to match your own solar panel setup.
PANEL_LENGTH_M = 1.72 # in meters, measured along the panel's longest side (the "portrait" orientation)
PANEL_WIDTH_M = 1.13 # in meters, measured along the panel's shortest side (the "portrait" orientation)
PANEL_RATED_POWER_W = 400 # in watts, the panel's rated power output under standard test conditions (STC)
PANEL_COUNT = 2
SYSTEM_AC_EFFICIENCY = 0.95 # Total inverter efficiency factor (accounting for DC-to-AC conversion losses, cable resistance, and minor system degradation)
PANEL_TILT_DEG = 26.5 # Panel tilt angle in degrees, measured relative to the horizontal ground (0° = flat, 90° = vertical)
PANEL_AZIMUTH_DEG = 35 #https://azimut.polka-umwelt.de/ # Panel orientation in degrees, measured as the offset from exact South clockwise towards West (0° = South, positive values = West)

# Temperature loss model constants. (Faiman-Model)
#
# Ground-mounted ((Free-standing / Field)) -> very good air circulation: U0=21.4, U1=4.02
# Vertically mounted (Solar Fence / Facade) -> Good to moderate airflow: U0=23.0, U1=3.1
# Roof-mounted (Parallel to the roof) -> Poor airflow + temp. from roof: U0=29.0, U1=4.4

U0 = 21.4 # Base heat transfer coefficient (influence of ambient temperature)
U1 = 4.02 # Wind cooling factor (cooling effect per m/s of wind speed)
TEMP_COEFF = -0.0038 # Temperature coefficient of the panel (-0.38% power per °C above 25°C)
################################################

PANEL_AREA_M2 = PANEL_LENGTH_M * PANEL_WIDTH_M
PANEL_STC_EFFICIENCY = PANEL_RATED_POWER_W / (1000 * PANEL_AREA_M2)

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
	return irradiance_w_m2 * PANEL_AREA_M2 * PANEL_STC_EFFICIENCY


def estimate_array_output_w(panel_output_w: float) -> float:
	return panel_output_w * PANEL_COUNT


def estimate_ac_output_w(array_output_w: float) -> float:
	return array_output_w * SYSTEM_AC_EFFICIENCY


def calculate_cell_temperature_and_loss(temp_ambient: float, wind_speed_ms: float, irradiance_w_m2: float) -> tuple[float, float]:
	if irradiance_w_m2 == 0.0:
		t_cell = temp_ambient
	else:
		t_cell = temp_ambient + (irradiance_w_m2 / (U0 + U1 * wind_speed_ms))

	if t_cell > 25.0:
		temp_loss_factor = 1.0 + (TEMP_COEFF * (t_cell - 25.0))
	else:
		temp_loss_factor = 1.0

	return t_cell, temp_loss_factor


def getWeatherAndSolarData(latitude: float, longitude: float, timezone_name: str) -> dict:
	url = (
		"https://api.open-meteo.com/v1/forecast"
		f"?latitude={latitude}&longitude={longitude}"
		"&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,global_tilted_irradiance,shortwave_radiation"
		f"&tilt={PANEL_TILT_DEG}&azimuth={PANEL_AZIMUTH_DEG}"
		f"&timezone={quote(timezone_name)}"
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
		temp_ambient = float(current.get("temperature_2m"))
		apparent_temperature = float(current.get("apparent_temperature"))
		wind_speed = float(current.get("wind_speed_10m"))
		wind_speed_ms = wind_speed / 3.6
		tilted_irradiance = float(tilted_irradiance_raw)
		horizontal_irradiance = float(horizontal_irradiance_raw)
		t_cell, temp_loss_factor = calculate_cell_temperature_and_loss(temp_ambient, wind_speed_ms, tilted_irradiance)

		panel_output_w = estimate_panel_output_w(tilted_irradiance)
		dc_output_w = estimate_array_output_w(panel_output_w) * temp_loss_factor
		ac_output_w = estimate_ac_output_w(dc_output_w)
		density_w_m2 = tilted_irradiance * PANEL_STC_EFFICIENCY
		return {
			"name": CITY_NAME,
			"country": COUNTRY_CODE,
			"temp_c": temp_c,
			"apparent_temperature": apparent_temperature,
			"description": desc,
			"humidity": humidity,
			"tilted_irradiance": tilted_irradiance,
			"horizontal_irradiance": horizontal_irradiance,
			"wind_speed_ms": wind_speed_ms,
			"t_cell": t_cell,
			"temp_loss_factor": temp_loss_factor,
			"panel_output_w": panel_output_w,
			"dc_output_w": dc_output_w,
			"ac_output_w": ac_output_w,
			"density_w_m2": density_w_m2,
		}
	except (TypeError, ValueError):
		return {
			"name": CITY_NAME,
			"country": COUNTRY_CODE,
			"temp_c": temp_c,
			"apparent_temperature": None,
			"description": desc,
			"humidity": humidity,
			"tilted_irradiance": None,
			"horizontal_irradiance": None,
			"wind_speed_ms": None,
			"t_cell": None,
			"temp_loss_factor": None,
			"panel_output_w": None,
			"dc_output_w": None,
			"ac_output_w": None,
			"density_w_m2": None,
		}


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
		solarAndWeatherData = getWeatherAndSolarData(
			location["latitude"],
			location["longitude"],
			location["timezone"],
		)
		current_time = get_time(location["timezone"])
	except (URLError, TimeoutError, KeyError, ValueError) as exc:
		print(f"Could not fetch live weather/time data: {exc}")
		return

	print("Current time:")
	print(current_time)
	print()  
	print("Current weather and estimated solar data:")

	formatted_output = (
    f"{solarAndWeatherData['name']}, {solarAndWeatherData['country']}: {solarAndWeatherData['temp_c']}°C, "
    f"feels like {solarAndWeatherData['apparent_temperature']:.1f}°C, {solarAndWeatherData['description']}, "
    f"humidity {solarAndWeatherData['humidity']}%, "
    f"tilted solar {solarAndWeatherData['tilted_irradiance']:.0f} W/m^2, "
    f"horizontal {solarAndWeatherData['horizontal_irradiance']:.0f} W/m^2, "
    f"panel {solarAndWeatherData['density_w_m2']:.0f} W/m^2, "
    f"wind {solarAndWeatherData['wind_speed_ms']:.1f} m/s, "
    f"t_cell {solarAndWeatherData['t_cell']:.1f}°C, loss {solarAndWeatherData['temp_loss_factor']:.3f}, "
    f"panel DC {solarAndWeatherData['panel_output_w']:.0f} W, array DC {solarAndWeatherData['dc_output_w']:.0f} W, "
    f"AC {solarAndWeatherData['ac_output_w']:.0f} W, tilt {PANEL_TILT_DEG}°, azimuth {PANEL_AZIMUTH_DEG}°"
)
	print(formatted_output)
	
if __name__ == "__main__":
	main()
