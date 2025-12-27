"""
Weather tool plugin for Krell.

Provides current weather and forecast information.
"""

from strands import tool
import requests
import os


@tool
def get_weather(location: str, days: int = 3) -> dict:
    """
    Get current weather and forecast for a location.

    Use this tool when the user asks about weather, temperature, or forecasts.

    Args:
        location: City name (e.g., "New York", "London") or coordinates
        days: Number of forecast days (1-5, default: 3)

    Returns:
        Dictionary with current weather and forecast data
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return {"error": "Weather API key not configured"}

    # Get current weather
    current_url = f"http://api.openweathermap.org/data/2.5/weather"
    params = {"q": location, "appid": api_key, "units": "imperial"}

    try:
        response = requests.get(current_url, params=params)
        response.raise_for_status()
        current_data = response.json()

        current = {
            "temp": round(current_data["main"]["temp"]),
            "feels_like": round(current_data["main"]["feels_like"]),
            "humidity": current_data["main"]["humidity"],
            "weather": current_data["weather"][0]["description"].title(),
            "wind_speed": current_data["wind"]["speed"],
        }

        # Get forecast
        forecast_url = f"http://api.openweathermap.org/data/2.5/forecast"
        forecast_response = requests.get(forecast_url, params=params)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        # Simplify forecast to daily highs/lows
        forecast = []
        daily_temps = {}

        for item in forecast_data["list"][: days * 8]:  # 3-hour intervals
            date = item["dt_txt"].split()[0]
            temp = item["main"]["temp"]

            if date not in daily_temps:
                daily_temps[date] = {
                    "high": temp,
                    "low": temp,
                    "condition": item["weather"][0]["description"],
                }
            else:
                daily_temps[date]["high"] = max(daily_temps[date]["high"], temp)
                daily_temps[date]["low"] = min(daily_temps[date]["low"], temp)

        for i, (date, temps) in enumerate(list(daily_temps.items())[1 : days + 1]):
            forecast.append(
                {
                    "day": f"Day {i + 1}" if i > 0 else "Tomorrow",
                    "high": round(temps["high"]),
                    "low": round(temps["low"]),
                    "condition": temps["condition"].title(),
                }
            )

        return {
            "location": current_data["name"],
            "current": current,
            "forecast": forecast[:days],
        }

    except requests.RequestException as e:
        return {"error": f"Failed to fetch weather data: {str(e)}"}
