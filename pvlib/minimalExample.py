import pandas as pd
import pvlib
from pvlib.location import Location

# 1. Define the location (latitude, longitude, timezone, altitude, name)
# Example: Berlin, Germany
loc = Location(
    latitude=52.5200, 
    longitude=13.4050, 
    tz='Europe/Berlin', 
    altitude=34, 
    name='Berlin'
)

# 2. Define a time range (1-minute intervals for a specific day)
times = pd.date_range(
    start='2026-06-21 05:00:00', 
    end='2026-06-21 21:00:00', 
    freq='1min', 
    tz=loc.tz
)

# 3. Calculate solar position (zenith, azimuth, etc.)
solpos = loc.get_solarposition(times)

# 4. Calculate clear-sky irradiance (GHI, DNI, DHI)
# Uses the Ineichen/Perez model by default
irradiance = loc.get_clearsky(times, model='ineichen', solar_position=solpos)

# 5. Print the first few results
print("--- Solar Position Example ---")
print(solpos[['zenith', 'azimuth']].head())

print("\n--- Clear-Sky Irradiance Example (W/m²) ---")
print(irradiance[['ghi', 'dni', 'dhi']].head())
