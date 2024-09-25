#!/usr/bin/env python3
# reset ttyS0 sudo stty -F /dev/ttyS0 sane
import logging
import queue
import signal
import termios
import threading
import time
from datetime import datetime
from gpiozero import CPUTemperature
import requests
import serial
import yaml
import subprocess
from influxdb import InfluxDBClient
import copy

from urllib3 import Retry
from urllib3.exceptions import HTTPError

from hoymiles_modbus.client import HoymilesModbusTCP
from hoymiles_modbus.datatypes import MicroinverterType

DEFAULT_KEYS = ('ISOUSC', 'BASE', 'IINST',)
DEFAULT_CHECKSUM_METHOD = 1

START_FRAME = b'\x02'  # STX, Start of Text
STOP_FRAME = b'\x03'   # ETX, End of Text

def get_solar_info(shared_data):
    while not shared_data['stop']:
        try:
            plant_data = HoymilesModbusTCP('192.168.1.76', microinverter_type=MicroinverterType.HM).plant_data
            # Lock to safely update shared data
            with shared_data['lock']:
                shared_data['object'] = plant_data
                shared_data['completed'] = True
            # Sleep a bit before next computation
        except Exception as e:
            # Catch the exception and pass
            print(f"Modbus exception: {e}")
            pass
        time.sleep(30)

def get_ups_info(shared_data):
    while not shared_data['stop']:
        try:
            # Run the apcaccess command to get UPS information
            output = subprocess.check_output(["apcaccess"])
    
            # Decode output bytes to string
            output = output.decode("utf-8")
    
            # Split output into lines
            lines = output.split('\n')
    
            # Initialize variables to store battery level and autonomy
            battery_level = None
            autonomy = None
    
            # Iterate through lines to find relevant information
            for line in lines:
                # Extract battery level
                if line.startswith('BCHARGE'):
                    battery_level = float(line.split(':')[1].strip().split(' ')[0])
    
                # Extract autonomy
                if line.startswith('TIMELEFT'):
                    autonomy = line.split(':')[1].strip().split(' ')[0]

            # Lock to safely update shared data
            with shared_data['lock']:
                if battery_level is not None and autonomy is not None:
                    shared_data['object'] = {'battery_level': battery_level, 'autonomy': autonomy}
                shared_data['completed'] = True
    
        except Exception as e:
            print(f"Error: Failed UPS request: {e}")
            pass
        time.sleep(10)

def get_internet_info(shared_data):
    while not shared_data['stop']:
        try:
            # Attempt to make a request to a reliable website
            response = requests.get("http://www.google.com", timeout=5)
            # If the request is successful, return True
            with shared_data['lock']:
                shared_data['object'] = {'conn': 1 if response.status_code == 200 else 0}
                shared_data['completed'] = True
            
        except Exception as e:
            print(f"Error: Failed internet request: {e}")
            pass
        time.sleep(30)
        
def _handler(signum, frame):
    logging.info('Programme interrompu par CTRL+C')
    raise SystemExit(0)


def _send_frames_to_influx():
    logging.debug(f'Thread d\'envoi vers InfluxDB démarré')

    while True:

        # Récupère une trame dans la file d'attente
        frame = frame_queue.get()
        ftime = frame.pop('TIME')
        record = []
        for measure, value in frame.items():
            point = {
                "measurement": measure,
                "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fields": {
                    "value": value
                }
            }
            record.append(point)

        # Envoie vers InfluxDB et ré-essaie en boucle tant que cela ne fonctionne pas
        logging.info(f'Ecriture dans InfluxDB')
        written = False
        x = 0
        while not written:
            try:
                client.write_points(record)
                written = True
            except ApiException as exc:
                if exc.status == 404:
                    logging.error(f'Le bucket {influxdb_bucket} n\'existe pas ${exc}')
                elif exc.status == 403:
                    logging.error(f'Permissions insufissantes pour écrire dans {influxdb_bucket}')
                else:
                    logging.error(f'Erreur lors de l\'écriture dans {influxdb_bucket}')
            except InfluxDBClientError as exc:
                logging.error(f'Erreur InfluxDB', exc_info=True)
            except (OSError, HTTPError) as exc:
                logging.error(f'Serveur injoignable', exc_info=True)
            finally:
                if not written:
                    # Attends de plus en plus longtemps
                    sleep = 2 ** x
                    logging.error(f'Nouvel essai dans {sleep} seconde(s)')
                    time.sleep(2 ** x)
                    # Mais pas trop quand même. max = 2**10 secondes, soit environ 17 minutes
                    if x < 10:
                        x += 1

        frame_queue.task_done()


def _checksum(key, val, separator, checksum):
    """Vérifie la somme de contrôle du groupe d'information. Réf Enedis-NOI-CPT_02E, page 19."""
    data = f'{key}{separator}{val}'
    if linky_checksum_method == 2:
        data += separator
    s = sum([ord(c) for c in data])
    s = (s & 0x3F) + 0x20
    return (checksum == chr(s))

def linky():
    # Shared data structure between threads
    shared_data = {
        'object': None,
        'completed': False,
        'stop': False,
        'lock': threading.Lock()
    }

    ups_data = {
        'object': None,
        'completed': False,
        'stop': False,
        'lock': threading.Lock()
    }

    internet_data = {
        'object': None,
        'completed': False,
        'stop': False,
        'lock': threading.Lock()
    }

    # Create and start the thread
    solar_worker_thread = threading.Thread(target=get_solar_info, args=(shared_data,))
    solar_worker_thread.start()
    ups_worker_thread = threading.Thread(target=get_ups_info, args=(ups_data,))
    ups_worker_thread.start()
    internet_worker_thread = threading.Thread(target=get_internet_info, args=(internet_data,))
    internet_worker_thread.start()
    # Ouverture du port série
    try:
        baudrate = 1200 if linky_legacy_mode else 9600
        logging.info(
            f'Ouverture du port série {raspberry_stty_port} à {baudrate} Bd')
        with serial.Serial(port=raspberry_stty_port,
                           baudrate=baudrate,
                           parity=serial.PARITY_EVEN,
                           stopbits=serial.STOPBITS_ONE,
                           bytesize=serial.SEVENBITS,
                           timeout=1) as ser:

            # Boucle pour partir sur un début de trame
            logging.info('Attente d\'une première trame...')
            line = ser.readline()
            while START_FRAME not in line:  # Recherche du caractère de début de trame, c'est-à-dire STX 0x02
                line = ser.readline()

            # Initialisation d'une trame vide
            frame = dict()

            # Boucle infinie
            while True:
                try:
                    # Lecture de la première ligne de la première trame
                    line = ser.readline()

                    # Décodage ASCII et nettoyage du retour à la ligne
                    line_str = line.decode('ascii').rstrip()
                    #logging.debug(f'Groupe d\'information brut : {line_str}')
                    print(f'line {line_str}')

                    # Récupération de la somme de contrôle (qui est le dernier caractère de la ligne)
                    checksum = line_str[-1]

                    # Identification du séparateur en vigueur (espace ou tabulation)
                    separator = line_str[-2]

                    # Position du séparateur entre le champ étiquette et le champ données
                    pos = line_str.find(separator)

                    # Extraction de l'étiquette
                    key = line_str[0:pos]

                    # Extraction de la donnée
                    val = line_str[pos+1:-2]

                    with shared_data['lock']:
                        if shared_data['completed']:
                            plant_data = copy.deepcopy(shared_data['object'])
                            shared_data['completed'] = False  # Reset completion status
                            # Solar
                            frame['SPPW'] = plant_data.pv_power
                            frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            frame_queue.put(frame)
                            frame = dict()
                            frame['SPPO'] = plant_data.today_production
                            frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            frame_queue.put(frame)
                            frame = dict()
                            panelIndex = 0
                            for entry in plant_data.microinverter_data:
                                panelPowerString = f"SPP{panelIndex}"
                                panelTemperatureString = f"SPT{panelIndex}"
                                #print(f"Microinverter ID: {entry.pv_power} {entry.temperature} {entry.serial_number}")
                                frame[panelPowerString] = entry.pv_power
                                frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                                frame_queue.put(frame)
                                frame = dict()
                                frame[panelTemperatureString] = entry.temperature
                                frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                                frame_queue.put(frame)
                                frame = dict()
                                panelIndex = panelIndex + 1


                    # Est-ce une étiquette qui nous intéresse ?
                    if key in linky_keys:
                        # Vérification de la somme de contrôle
                        if _checksum(key, val, separator, checksum):
                            # Ajout de la valeur
                            frame[key] = int(val)
                        else:
                            logging.debug(
                                f'Somme de contrôle erronée pour {key}')

                    # Si caractère de fin de trame dans la ligne, on écrit les données dans InfluxDB
                    if STOP_FRAME in line:
                        num_keys = len(frame)
                        logging.info(f'Trame reçue ({num_keys} étiquettes traités)')

                        # Horodatage de la trame reçue
                        frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                        # Ajout à la queue d'envoi vers InfluxDB
                        if influxdb_send_data:
                            frame_queue.put(frame)

                        # On réinitialise  une nouvelle trame
                        frame = dict()
                        # temp
                        cpu_temp = CPUTemperature()
                        frame['TEMP'] = cpu_temp.temperature
                        frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                        frame_queue.put(frame)
                        frame = dict()
                        # connection
                    with internet_data['lock']:
                        if internet_data['completed']:
                            conn = copy.deepcopy(internet_data['object'])
                            internet_data['completed'] = False  # Reset completion status
                            frame['CONN'] = conn['conn']
                            frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            frame_queue.put(frame)
                            frame = dict()
                        #UPS
                    with ups_data['lock']:
                        if ups_data['completed']:
                            ups = copy.deepcopy(ups_data['object'])
                            ups_data['completed'] = False  # Reset completion status
                            #print(ups)
                            #battery_level, autonomy = get_battery_info()
                            frame['UPSL'] = ups['battery_level']
                            frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            frame_queue.put(frame)
                            frame = dict()
                            frame['UPSA'] = ups['autonomy']
                            frame['TIME'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            frame_queue.put(frame)
                            frame = dict()
                        #time.sleep(4)

                except Exception as e:
                    logging.error(f'Une exception s\'est produite : {e}', exc_info=True)
                    logging.error(f'Etiquette : {key}  Donnée : {val}')

    except termios.error:
        logging.error('Erreur lors de la configuration du port série')
        if raspberry_stty_port == '/dev/ttyS0':
            logging.error('Essayez d\'utiliser /dev/ttyAMA0 plutôt que /dev/ttyS0')
        raise SystemExit(1)

    """ except serial.SerialException as exc:
        if exc.errno == 13:
            logging.error('Erreur de permission sur le port série')
            logging.error('Avez-vous ajouté l\'utilisateur au groupe dialout ?')
            logging.error('  $ sudo usermod -G dialout $USER')
            logging.error(
                'Vous devez vous déconnecter de votre session puis vous reconnecter pour que les droits prennent effet.')
        else:
            logging.error(f'Erreur lors de l\'ouverture du port série : {exc}')
        raise SystemExit(1) """


if __name__ == '__main__':

    # Creation du logger
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logging.info('Démarrage Linky Téléinfo')

    # Capture élégamment une interruption par CTRL+C
    signal.signal(signal.SIGINT, _handler)

    # Lecture du fichier de configuration
    try:
        with open("config.yml", "r") as f:
            cfg = yaml.load(f, Loader=yaml.SafeLoader)
    except FileNotFoundError:
        logging.error('Il manque le fichier de configuration config.yml')
        raise SystemExit(1)
    except yaml.YAMLError as exc:
        if hasattr(exc, 'problem_mark'):
            mark = exc.problem_mark
            logging.error('Le fichier de configuration comporte une erreur de syntaxe')
            logging.error(f'La position de l\'erreur semble être en ligne {mark.line+1} colonne {mark.column+1}')
            raise SystemExit(1)
    except (OSError, IOError):
        logging.error('Erreur de lecture du fichier config.yml. Vérifiez les permissions ?')
        raise SystemExit(1)
    except Exception:
        logging.critical('Erreur lors de la lecture du fichier de configuration', exc_info=True)
        raise SystemExit(1)

    try:
        debug = cfg.get('debug', False)
        linky_location = cfg['linky']['location']
        linky_legacy_mode = cfg['linky']['legacy_mode']
        linky_checksum_method = cfg['linky'].get('checksum_method', DEFAULT_CHECKSUM_METHOD)
        linky_keys = cfg['linky'].get('keys', DEFAULT_KEYS)
        raspberry_stty_port = cfg['raspberry']['stty_port']
        influxdb_send_data = cfg['influxdb']['send_data']
        if influxdb_send_data:
            influxdb_url = cfg['influxdb']['url']
            influxdb_bucket = cfg['influxdb']['bucket']
            influxdb_token = cfg['influxdb']['token']
            influxdb_org = cfg['influxdb']['org']
    except KeyError as exc:
        logging.error(f'Erreur : il manque la clé {exc} dans le fichier de configuration')
        raise SystemExit(1)
    except Exception:
        logging.critical('Erreur lors de la lecture du fichier de configuration', exc_info=True)
        raise SystemExit(1)

    # Configuration du logger en mode debug
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Création d'une queue FIFO pour stocker les données
    frame_queue = queue.Queue()

    write_client = None
    if influxdb_send_data:
        # Connexion à InfluxDB
        try:
            logging.info(f'Connexion à {influxdb_url}')
            retries = Retry(connect=4, read=2, redirect=5, backoff_factor=0.5)
            #influx_client = InfluxDBClient(url=influxdb_url,
            #                               token=influxdb_token,
            #                               org=influxdb_org,
            #                               retries=retries)
            #influx_client.switch_database(influxdb_bucket)
            client = InfluxDBClient('pi.local', 8086)
            client.switch_database(influxdb_bucket)
        except InfluxDBClientError as exc:
            logging.error(f'Erreur de connexion à InfluxDB: {exc}')
            raise SystemExit(1)

        # Obtention du client d'API en écriture
        #point_settings = PointSettings()
        #point_settings.add_default_tag('location', linky_location)
        #write_client = influx_client.write_api(write_options=SYNCHRONOUS, point_settings=point_settings)

        # Démarrage du thread d'envoi vers InfluxDB
        logging.debug(f'Démarrage du thread d\'envoi vers InfluxDB')
        send_thread = threading.Thread(target=_send_frames_to_influx, daemon=True)
        send_thread.start()

    # Lance la boucle infinie de lecture de la téléinfo
    linky()
