from hoymiles_modbus.client import HoymilesModbusTCP
from hoymiles_modbus.datatypes import MicroinverterType

plant_data = HoymilesModbusTCP(
    '192.168.1.76', microinverter_type=MicroinverterType.HM).plant_data
print(plant_data.today_production)
print(plant_data)
