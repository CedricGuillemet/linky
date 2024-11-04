import pygatt
from binascii import hexlify

# Replace with the MAC address of your BLE device
DEVICE_ADDRESS = "A4:C1:38:2E:0F:6E"
HANDLE = 0x0038  # The handle to which we are writing
VALUE = "0100"  # The value to write, in hexadecimal

def notification_handler(handle, value):
    # This function will be called when data is received from the device
    print(f"Notification from handle {handle}: {hexlify(value)}")

# Initialize the Bluetooth adapter (e.g., for Linux systems)
adapter = pygatt.GATTToolBackend()

try:
    # Start the adapter and connect to the device
    adapter.start()
    device = adapter.connect(DEVICE_ADDRESS)

    # Write the specified value to the handle to enable notifications
    device.char_write_handle(HANDLE, bytes.fromhex(VALUE), wait_for_response=True)
    
    # Subscribe to the handle to listen for notifications
    print("Listening for notifications...")
    device.subscribe(HANDLE, callback=notification_handler)

    # Keep the script running to continuously receive notifications
    input("Press Enter to exit...\n")

finally:
    # Disconnect and stop the adapter
    device.disconnect()
    adapter.stop()
