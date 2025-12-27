import pytest
import requests
from plugins.weather_tool import get_weather
from unittest.mock import patch, Mock


def test_get_weather_returns_current_and_forecast():
    # Mock environment to have API key
    with patch("plugins.weather_tool.os.getenv", return_value="test_api_key"):
        # Mock the API responses
        mock_current_response = Mock()
        mock_current_response.json.return_value = {
            "name": "New York",
            "main": {"temp": 72, "feels_like": 75, "humidity": 65},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 5.5},
        }

        mock_forecast_response = Mock()
        mock_forecast_response.json.return_value = {
            "list": [
                # Today - should be skipped in forecast
                {
                    "dt_txt": "2025-12-07 00:00:00",
                    "main": {"temp": 70},
                    "weather": [{"description": "clear sky"}],
                },
                {
                    "dt_txt": "2025-12-07 03:00:00",
                    "main": {"temp": 68},
                    "weather": [{"description": "clear sky"}],
                },
                {
                    "dt_txt": "2025-12-07 06:00:00",
                    "main": {"temp": 65},
                    "weather": [{"description": "clear sky"}],
                },
                {
                    "dt_txt": "2025-12-07 09:00:00",
                    "main": {"temp": 72},
                    "weather": [{"description": "clear sky"}],
                },
                # Tomorrow
                {
                    "dt_txt": "2025-12-08 00:00:00",
                    "main": {"temp": 75},
                    "weather": [{"description": "partly cloudy"}],
                },
                {
                    "dt_txt": "2025-12-08 03:00:00",
                    "main": {"temp": 70},
                    "weather": [{"description": "partly cloudy"}],
                },
                {
                    "dt_txt": "2025-12-08 06:00:00",
                    "main": {"temp": 68},
                    "weather": [{"description": "partly cloudy"}],
                },
                {
                    "dt_txt": "2025-12-08 09:00:00",
                    "main": {"temp": 78},
                    "weather": [{"description": "partly cloudy"}],
                },
                # Day 2
                {
                    "dt_txt": "2025-12-09 00:00:00",
                    "main": {"temp": 80},
                    "weather": [{"description": "sunny"}],
                },
                {
                    "dt_txt": "2025-12-09 03:00:00",
                    "main": {"temp": 75},
                    "weather": [{"description": "sunny"}],
                },
                {
                    "dt_txt": "2025-12-09 06:00:00",
                    "main": {"temp": 72},
                    "weather": [{"description": "sunny"}],
                },
                {
                    "dt_txt": "2025-12-09 09:00:00",
                    "main": {"temp": 85},
                    "weather": [{"description": "sunny"}],
                },
            ]
        }

        with patch("plugins.weather_tool.requests.get") as mock_get:
            mock_get.side_effect = [mock_current_response, mock_forecast_response]
            result = get_weather(location="New York")

    assert isinstance(result, dict)
    assert "current" in result
    assert "forecast" in result
    assert result["current"]["temp"] == 72
    assert len(result["forecast"]) == 2
    assert result["forecast"][0]["day"] == "Tomorrow"
    assert result["forecast"][1]["day"] == "Day 2"


def test_get_weather_handles_api_errors():
    with patch("plugins.weather_tool.os.getenv", return_value="test_api_key"):
        with patch("plugins.weather_tool.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("API Error")

            result = get_weather(location="Invalid City")

            assert "error" in result
            assert "Failed to fetch" in result["error"]


def test_get_weather_handles_missing_api_key():
    with patch("plugins.weather_tool.os.getenv", return_value=None):
        result = get_weather(location="New York")

        assert result["error"] == "Weather API key not configured"
