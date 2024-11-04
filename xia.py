import pygatt
from binascii import hexlify

# Replace with the MAC address of your BLE device
DEVICE_ADDRESS = "A4:C1:38:2E:0F:6E"
HANDLE = 0x0038
VALUE = "0100"

def notification_handler(handle, value):
    print(f"Notification from handle {handle}: {hexlify(value)}")

# Initialize the Bluetooth adapter (e.g., for Linux systems)
adapter = pygatt.GATTToolBackend()

try:
    # Start the adapter and connect to the device
    adapter.start()
    device = adapter.connect(DEVICE_ADDRESS)

    # Write the specified value to the handle
    device.char_write_handle(HANDLE, bytes.fromhex(VALUE), wait_for_response=True)
    
    # Enable notifications and listen
    print("Listening for notifications...")
    device.subscribe(HANDLE, callback=notification_handler)

    # Keep the script running to receive notifications
    input("Press Enter to exit...\n")

finally:
    # Disconnect and stop the adapter
    device.disconnect()
    adapter.stop()
