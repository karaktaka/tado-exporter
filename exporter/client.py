from os import getenv
from time import sleep
from libtado.api import Tado
from prometheus_client import start_http_server, Gauge


if __name__ == "__main__":
    # Start up the server to expose the metrics.
    username = getenv("TADO_USERNAME")
    password = getenv("TADO_PASSWORD")
    client_secret = getenv("TADO_CLIENT_SECRET")
    temperature_unit = getenv("TADO_TEMPERATURE_UNIT", "celsius")
    refresh_rate = int(getenv("TADO_EXPORTER_REFRESH_RATE", 30))
    loglevel = getenv("LOGLEVEL", "INFO")

    # set logging level
    log = set_logging_level(loglevel)

    print("Starting tado exporter")
    start_http_server(8000)

    print(f"Connecting to tado API using account {username}")
    try:
        tado = Tado(username, password, client_secret)
    except KeyError:
        print("Authentication failed. Check your username, password or client secret.")
        exit(1)

    ACTIVITY_HEATING_POWER = Gauge(
        "tado_activity_heating_power_percentage",
        "The % of heating power in a specific zone.",
        ["zone", "type"]
    )
    ACTIVITY_AC_POWER = Gauge(
        "tado_activity_ac_power_value",
        "The value of ac power in a specific zone.",
        ["zone", "type"]
    )
    SETTING_TEMPERATURE = Gauge(
        "tado_setting_temperature_value",
        "The temperature of a specific zone in celsius degres.",
        ["zone", "type", "unit"]
    )
    SENSOR_TEMPERATURE = Gauge(
        "tado_sensor_temperature_value",
        "The temperature of a specific zone in celsius degres",
        ["zone", "type", "unit"]
    )
    SENSOR_HUMIDITY_PERCENTAGE = Gauge(
        "tado_sensor_humidity_percentage",
        "The % of humidity in a specific zone.",
        ["zone", "type"]
    )
    WEATHER_OUTSIDE_TEMPERATURE = Gauge(
        "weather_outside_temperature",
        "Temperature outside the house.",
        ["unit"]
    )
    SENSOR_WINDOW_OPENED = Gauge(
        "tado_sensor_window_opened",
        "1 if the sensor detected a window is open, 0 otherwise.",
        ["zone", "type"]
    )

    print("Exporter ready")
    while True:
        # noinspection PyBroadException
        try:
            for zone in tado.get_zones():
                activity_data = tado.get_state(zone["id"])["activityDataPoints"]
                setting_data = tado.get_state(zone["id"])["setting"]
                sensor_data = tado.get_state(zone["id"])["sensorDataPoints"]

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
                    ACTIVITY_AC_POWER.labels(zone["name"], zone["type"]).set(
                        activity_data["acPower"]["value"]
                    )
                if "openWindow" in tado.get_state(zone["id"]) and tado.get_state(zone["id"])["openWindow"] is not None:
                    SENSOR_WINDOW_OPENED.labels(zone["name"], zone["type"]).set(
                        tado.get_state(zone["id"])["openWindow"]
                    )
        except Exception:
            print("Cannot read data from Tado API. Will retry later.")
        finally:
            sleep(refresh_rate)
