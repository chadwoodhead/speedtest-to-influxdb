import sys
import time
import json
import subprocess
import os
import argparse
import configparser

from influxdb import InfluxDBClient
from datetime import datetime

parser = argparse.ArgumentParser(description='Run a Speedtest and store results in InfluxDB')

parser.add_argument("-v", "--verbose", help="Run in verbose mode", action="store_true")
args = parser.parse_args()

def read_ini(file_path):
    read_ini.config = configparser.ConfigParser()
    read_ini.config.read(file_path)
 
read_ini("config.ini")

#Read in generic settings
ENVIRONMENT = read_ini.config['APP']['ENVIRONMENT']
DEBUG = read_ini.config['APP']['DEBUG']

#Read in InfluxDB settings
DB_USERNAME = read_ini.config['DATABASE']['DB_USERNAME']
DB_PASSWORD = read_ini.config['DATABASE']['DB_PASSWORD']
DB_HOST = read_ini.config['DATABASE']['DB_HOST']
DB_PORT = read_ini.config['DATABASE']['DB_PORT']
DB_DATABASE = read_ini.config['DATABASE']['DB_DATABASE']
DB_RETRY_INVERVAL = read_ini.config['DATABASE']['DB_RETRY_INVERVAL']

#Read in Speedtest settings
TEST_INTERVAL = read_ini.config['SPEEDTEST']['TEST_INTERVAL']
TEST_FAIL_INTERVAL = read_ini.config['SPEEDTEST']['TEST_FAIL_INTERVAL']
TEST_SERVER_ID = read_ini.config['SPEEDTEST']['TEST_SERVER_ID']

if args.verbose:
    PRINT_DATA = True # Do you want to see the results in your logs?
else:
    PRINT_DATA = False # Do you want to see the results in your logs?

influxdb_client = InfluxDBClient(
    DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, None)

def str2bool(v):
  return v.lower() in ("yes", "true", "t", "1")

def logger(level, message):
    print(level, ":", datetime.now().strftime("%d/%m/%Y %H:%M:%S"), ":", message)

def init_db():
    try:
        databases = influxdb_client.get_list_database()
    except:
        logger("Error", "Unable to get list of databases")
        raise RuntimeError("No DB connection") from error
    else:
        if len(list(filter(lambda x: x['name'] == DB_DATABASE, databases))) == 0:
            influxdb_client.create_database(
                DB_DATABASE)  # Create if does not exist.
        else:
            influxdb_client.switch_database(DB_DATABASE)  # Switch to if does exist.


def format_for_influx(cliout):
    data = json.loads(cliout)
    # There is additional data in the speedtest-cli output but it is likely not necessary to store.
    influx_data = [
        {
            'measurement': 'speedtest',
            'time': data['timestamp'],
            'fields': {
                'download-bandwidth': data['download']['bandwidth'] / 125000,
                'download-bytes': data['download']['bytes'],
                'download-elapsed': data['download']['elapsed'],
                'upload-bandwidth': data['upload']['bandwidth'] / 125000,
                'upload-bytes': data['upload']['bytes'],
                'upload-elapsed': data['upload']['elapsed'],
                'jitter': float(data['ping']['jitter']),
                'latency': float(data['ping']['latency']),
                'packetloss': float(data.get('packetLoss', 0.0)),
                'interface-name': data['interface']['name'],
                'testserver-id': data['server']['id'],
                'testserver-name': data['server']['name'],
                'testserver-host': data['server']['host'],
                'testserver-ip': data['server']['ip'],
                'testserver-location': data['server']['location'],
                'testserver-country': data['server']['country'],
                'isp': data['isp']
            }
        }
    ]
    return influx_data


def main():
    db_initialized = False

    while(db_initialized == False):
        try:
            logger("Info", "Initializing DB")
            init_db()  # Setup the database if it does not already exist.
        except:
            logger("Error", "DB initialization error")
            #time.sleep(int(DB_RETRY_INVERVAL))
            sys.exit()
        else:
            logger("Info", "DB initialization complete")
            db_initialized = True

    # Run a Speedtest and send the results to influxDB.
    logger("Info", "Running speedtest")
    speedtest = subprocess.run(
        ["speedtest", "--accept-license", "--accept-gdpr", "-f", "json", "-s", TEST_SERVER_ID], capture_output=True)

    if speedtest.returncode == 0:  # Speedtest was successful.
        data = format_for_influx(speedtest.stdout)
        logger("Info", "Speedtest successful")
        if PRINT_DATA == True:
            logger("Info", data)
        try:
            logger("Info", "Writing data to DB")
            if influxdb_client.write_points(data) == True:
                logger("Info", "Data written to DB successfully")
        except:
            logger("Error", "Data write to DB failed")
            #time.sleep(TEST_FAIL_INTERVAL)
            sys.exit()
    else:  # Speedtest failed.
        logger("Error", "Speedtest failed")
        logger("Error", speedtest.stderr)
        logger("Info", speedtest.stdout)
        #time.sleep(TEST_FAIL_INTERVAL)
        sys.exit()
    logger('Info', 'Speedtest CLI Data Logger to InfluxDB completed')


if __name__ == '__main__':
    logger('Info', 'Speedtest CLI Data Logger to InfluxDB started')
    main()