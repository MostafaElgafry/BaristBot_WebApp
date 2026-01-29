#!/usr/bin/env python3
"""
Simple serial connection test script for COM6
"""
import serial
import time

def test_serial_connection():
    """Connect to COM6 and send a test message."""
    port = 'COM6'
    baudrate = 115200
    timeout = 2.0
    
    try:
        print(f"Attempting to connect to {port} at {baudrate} baud...")
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=timeout
        )
        print(f"✓ Connected to {port}")
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.15)
        
        # Send message
        message = "hello barista bot\n"
        print(f"Sending: {message.strip()}")
        ser.write(message.encode())
        
        # Wait a bit and try to read response
        time.sleep(0.5)
        
        if ser.in_waiting:
            response = ser.read(ser.in_waiting)
            print(f"Received: {response.decode('utf-8', errors='ignore')}")
        else:
            print("No response received (timeout or no data)")
        
        ser.close()
        print(f"✓ Closed connection to {port}")
        
    except serial.SerialException as e:
        print(f"✗ Serial error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == '__main__':
    test_serial_connection()
