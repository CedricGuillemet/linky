from bluepy.btle import Peripheral, UUID, DefaultDelegate
import struct

class MyDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleNotification(self, cHandle, data):
        # Handle the notification
        if len(data) < 5:
            print("Received notification with insufficient data.")
            return

        # Extract the temperature bytes (first two bytes)
        temp_high = data[0]
        temp_low = data[1]
        
        # Swap the two bytes and convert to decimal
        temperature = (temp_low << 8) | temp_high  # Low byte first, then high byte
        if temperature > 10000:  # Check for negative temperatures
            temperature -= 65536  # Convert to negative if above 10000

        # Convert to Celsius
        temperature_celsius = temperature / 100.0  # Assuming temperature is in hundredths of degrees

        # Extract humidity (third byte)
        humidity = data[2]

        # Print results
        print(f"Temperature: {temperature_celsius:.2f} °C")
        print(f"Humidity: {humidity} %")

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
