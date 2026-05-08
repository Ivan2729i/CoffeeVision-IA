import cv2
import sys

CAM_INDEX = 0  # cambia a 1 si quieres probar /dev/video1

cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

if not cap.isOpened():
    print(f"No se pudo abrir la cámara /dev/video{CAM_INDEX}")
    sys.exit(1)

print(f"Cámara abierta correctamente: /dev/video{CAM_INDEX}")
print("Presiona ESC para salir.")

while True:
    ret, frame = cap.read()

    if not ret or frame is None:
        print("No se pudo leer el frame")
        break

    cv2.imshow("Prueba Camara OpenCV", frame)

    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()