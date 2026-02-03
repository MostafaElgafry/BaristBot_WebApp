import serial, time, sys, binascii
port = 'COM6'
baud = 115200
send_variants = [b'CHECK\n', b'CHECK\r\n', b'CHECK\r']
try:
    for rtscts in (False, True):
        for dsrdtr in (False, True):
            print(f"=== open port rtscts={rtscts} dsrdtr={dsrdtr} ===")
            ser = serial.Serial(port, baud, timeout=0.2, write_timeout=0.5, rtscts=rtscts, dsrdtr=dsrdtr)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            for msg in send_variants:
                print(f"-- sending {msg!r}")
                ser.write(msg)
                ser.flush()
                deadline = time.time() + 2.0
                buf = b''
                while time.time() < deadline:
                    if ser.in_waiting:
                        chunk = ser.read(ser.in_waiting)
                        buf += chunk
                        ts = time.strftime('%H:%M:%S')
                        print(f"[{ts}] HEX:{binascii.hexlify(chunk).decode()} ASCII:{chunk.decode('ascii',errors='replace')!r}")
                    time.sleep(0.05)
                if not buf:
                    print("  (no response for this message)\n")
            ser.close()
except Exception as e:
    print("Error:", e)
    sys.exit(1)