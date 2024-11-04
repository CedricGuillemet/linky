from bluepy.btle import Peripheral, UUID, DefaultDelegate
import struct

class MyDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleNotification(self, cHandle, data):
        # Handle the notification
        print(f"Notification from handle {cHandle}: {data.hex()}")

def main():
    # Replace with your device's MAC address
    device_address = "A4:C1:38:2E:0F:6E"
    handle = 0x0038  # The handle to write to
    value = b'\x01\x00'  # The value to write (0100)

    try:
        # Connect to the BLE device
        device = Peripheral(device_address)

        # Set the delegate to handle notifications
        device.setDelegate(MyDelegate())

        # Write to the characteristic
        device.writeCharacteristic(handle, value, withResponse=True)

        # Listen for notifications
        print("Listening for notifications...")
        while True:
            if device.waitForNotifications(1.0):  # Wait for a notification for 1 second
                continue  # Notification was handled in the delegate
            print("Waiting...")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        device.disconnect()  # Ensure we disconnect when done

if __name__ == "__main__":
    main()
