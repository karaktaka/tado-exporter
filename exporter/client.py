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
    temp = Gauge(
        "tado_temperature",
        "Temperature as read by the sensor",
        labelnames=["zone_name"],
        unit="celsius",
    )
    humi = Gauge(
        "tado_humidity",
        "Humidity as read by the sensor",
        labelnames=["zone_name"],
        unit="percentage",
    )
    heat = Gauge(
        "tado_heating", "Heating power", labelnames=["zone_name"], unit="percentage"
    )
    print("Exporter ready")
    while True:
        # noinspection PyBroadException
        try:
            for zone in tado.get_zones():
                temp.labels("zone_" + str(zone["id"])).set(
                    tado.get_state(zone["id"])["sensorDataPoints"]["insideTemperature"][
                        "celsius"
                    ]
                )
                humi.labels("zone_" + str(zone["id"])).set(
                    tado.get_state(zone["id"])["sensorDataPoints"]["humidity"][
                        "percentage"
                    ]
                )
                heat.labels("zone_" + str(zone["id"])).set(
                    tado.get_state(zone["id"])["activityDataPoints"]["heatingPower"][
                        "percentage"
                    ]
                )
        except Exception:
            print("Cannot read data from Tado API. Will retry later.")
        finally:
            sleep(refresh_rate)
