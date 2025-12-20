# -*- coding: utf-8 -*-
"""
Tado Exporter Client
This script connects to the Tado API and exports various metrics related to temperature, humidity, and
heating/AC activity to Prometheus.
"""

import logging
from os import getenv
from time import sleep

import requests.exceptions
from libtado.api import Tado
from prometheus_client import Gauge, start_http_server
from requests.exceptions import HTTPError

ACTIVITY_HEATING_POWER = Gauge(
    "tado_activity_heating_power_percentage",
    "The % of heating power in a specific zone.",
    ["zone", "type"],
)
ACTIVITY_AC_POWER = Gauge(
    "tado_activity_ac_power_value",
    "The value of ac power in a specific zone.",
    ["zone", "type"],
)
SETTING_TEMPERATURE = Gauge(
    "tado_setting_temperature_value",
    "The temperature of a specific zone in celsius degrees.",
    ["zone", "type", "unit"],
)
SENSOR_TEMPERATURE = Gauge(
    "tado_sensor_temperature_value",
    "The temperature of a specific zone in celsius degrees",
    ["zone", "type", "unit"],
)
SENSOR_HUMIDITY_PERCENTAGE = Gauge(
    "tado_sensor_humidity_percentage",
    "The % of humidity in a specific zone.",
    ["zone", "type"],
)
WEATHER_OUTSIDE_TEMPERATURE = Gauge("weather_outside_temperature", "Temperature outside the house.", ["unit"])
SENSOR_WINDOW_OPENED = Gauge(
    "tado_sensor_window_opened",
    "1 if the sensor detected a window is open, 0 otherwise.",
    ["zone", "type"],
)


def set_logging_level(_level, _logger=None):
    _fmt = logging.Formatter(
        "%(asctime)s - %(module)s:%(lineno)d - %(levelname)s:%(message)s",
        datefmt="%d.%m.%Y %H:%M:%S",
    )

    # Logger
    if _logger is None:
        _logger = logging.getLogger(__name__)

    _ch = logging.StreamHandler()
    _ch.setFormatter(_fmt)

    _logger.addHandler(_ch)
    _logger.setLevel(_level)
    _logger.info(f"Setting loglevel to {_level}.")

    return _logger


def retry(_header, _max_retries: int):
    _retry_after = None
    if _max_retries <= 0:
        log.error("Maximum retries reached. Exiting.")
        return False
    _rate_limit_header = _header.get("RateLimit", "")
    for _part in _rate_limit_header.split(";"):
        if _part.strip().startswith("t="):
            _retry_after = int(_part.strip()[2:])
    if _retry_after:
        log.error(f"Tado API rate limit exceeded. Retrying after {_retry_after} seconds.")
        sleep(_retry_after)
        _max_retries -= 1
    return True, _max_retries


if __name__ == "__main__":
    tado = None

    # Read configuration from environment variables
    temperature_unit = getenv("TADO_TEMPERATURE_UNIT", "celsius")
    refresh_rate = int(getenv("TADO_EXPORTER_REFRESH_RATE", 30))
    max_retries = int(getenv("TADO_API_MAX_RETRIES", 5))
    loglevel = getenv("LOGLEVEL", "INFO")

    # set logging level
    log = set_logging_level(loglevel)

    # Connect to Tado API
    log.info("Connecting to tado API...")
    while True:
        try:
            tado = Tado(token_file_path="refresh_token.json")
            status = tado.get_device_activation_status()

            if status == "PENDING":
                tado.device_activation()
            log.info("Connected to Tado API")
            break
        except (KeyError, HTTPError) as error:
            if error.response.status_code == requests.codes.too_many_requests:
                retry, max_retries = retry(error.response.headers, max_retries)
                if retry:
                    continue
                exit(1)
            elif (
                isinstance(error, KeyError)
                or [requests.codes.unauthorized, requests.codes.forbidden] in error.response.status_code
            ):
                log.error("Authentication failed. Please check your credentials.")
            exit(2)

    # Start the Prometheus metrics server
    log.info("Starting tado exporter")
    start_http_server(8000)
    log.info("Exporter ready")
    while True:
        try:
            for zone in tado.get_zones():
                data = tado.get_state(zone["id"])
                activity_data = data.get("activityDataPoints")
                setting_data = data.get("setting")
                sensor_data = data.get("sensorDataPoints")
                open_window = data.get("openWindow")

                if "temperature" in setting_data and setting_data["temperature"] is not None:
                    SETTING_TEMPERATURE.labels(zone["name"], zone["type"], temperature_unit).set(
                        setting_data["temperature"][temperature_unit]
                    )
                if "insideTemperature" in sensor_data:
                    SENSOR_TEMPERATURE.labels(zone["name"], zone["type"], temperature_unit).set(
                        sensor_data["insideTemperature"][temperature_unit]
                    )
                if "humidity" in sensor_data:
                    SENSOR_HUMIDITY_PERCENTAGE.labels(zone["name"], zone["type"]).set(
                        sensor_data["humidity"]["percentage"]
                    )
                if "heatingPower" in activity_data:
                    ACTIVITY_HEATING_POWER.labels(zone["name"], zone["type"]).set(
                        activity_data["heatingPower"]["percentage"]
                    )
                if "acPower" in activity_data:
                    ACTIVITY_AC_POWER.labels(zone["name"], zone["type"]).set(activity_data["acPower"]["value"])
                SENSOR_WINDOW_OPENED.labels(zone["name"], zone["type"]).set(
                    1 if tado.get_state(zone["id"])["openWindow"] is not None else 0
                )
        except HTTPError as error:
            if error.response.status_code == requests.codes.too_many_requests:
                retry, max_retries = retry(error.response.headers, max_retries)
                if retry:
                    continue
                exit(1)
            log.debug(error)
        except Exception as error:
            log.error("Cannot read data from Tado API. Will retry later.")
            log.debug(error)
        finally:
            sleep(refresh_rate)
