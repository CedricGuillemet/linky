from atc_mi_interface import AtcMiInterface

# Initialize the interface (specify the appropriate connection parameters)
interface = AtcMiInterface()

# Connect to the interface
interface.connect()

# Define the MAC address
mac_address = "A4:C1:38:2E:0F:6E"

# Function to get information from the MAC address
def get_info_from_mac(mac):
    # Assuming there's a method to get info by MAC address
    info = interface.get_device_info(mac)
    return info

# Get the information for the specified MAC address
device_info = get_info_from_mac(mac_address)

# Print the device information
print(device_info)

# Don't forget to disconnect after the operation
interface.disconnect()
