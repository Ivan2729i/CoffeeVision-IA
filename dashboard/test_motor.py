import time
import serial

ser = serial.Serial("COM5", 115200, timeout=1)

# El ESP32 puede reiniciarse al abrir el puerto
time.sleep(2)

print("Mandando velocidad 50%...")
ser.write(b"V50\n")
time.sleep(0.2)
print(ser.readline().decode(errors="ignore").strip())

print("Encendiendo motor...")
ser.write(b"E\n")
time.sleep(3)

print("Deteniendo motor...")
ser.write(b"S\n")
time.sleep(0.2)
print(ser.readline().decode(errors="ignore").strip())

ser.close()
print("Prueba terminada.")
