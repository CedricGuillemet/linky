from bluepy.btle import Peripheral, DefaultDelegate
import struct
import argparse
import time

class MyDelegate(DefaultDelegate):
    def __init__(self, device_address):
        super().__init__()
        self.device_address = device_address

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
        print(f"Temperature: {temperature_celsius:.2f} °C, Humidity: {humidity} %")
        
        # Stop listening after the first notification
        return True  # Return True to indicate that we want to stop listening

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Read temperature and humidity from a Bluetooth device.")
    parser.add_argument("device_address", help="The MAC address of the Bluetooth device")
    args = parser.parse_args()

    device_address = args.device_address
    handle = 0x0038  # The handle to write to
    value = b'\x01\x00'  # The value to write (0100)

    try:
        # Connect to the BLE device
        device = Peripheral(device_address)

        # Set the delegate to handle notifications
        delegate = MyDelegate(device_address)
        device.setDelegate(delegate)

        # Write to the characteristic
        device.writeCharacteristic(handle, value, withResponse=True)

        # Listen for notifications
        print(f"Listening for notifications from {device_address}...")
        
        # Loop to listen for notifications only once
        while True:
            if device.waitForNotifications(60.0):  # Wait for a notification for 60 seconds
                break  # Exit the loop after receiving the first notification
            #print("Waiting...")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        device.disconnect()  # Ensure we disconnect when done

if __name__ == "__main__":
    main()
