import cv2
VIDEO = r"C:\dream11_project\videos\clip.mp4"
ROI = (895, 345, 80, 150)
FRAME = 0   # try a later frame (e.g. 150) to see the stumps near the end

cap = cv2.VideoCapture(VIDEO)
cap.set(cv2.CAP_PROP_POS_FRAMES, FRAME)
ok, f = cap.read()
cap.release()
x, y, w, h = ROI
cv2.rectangle(f, (x, y), (x + w, y + h), (0, 255, 0), 2)
crop = f[max(0, y - 100):y + h + 100, max(0, x - 150):x + w + 150]
crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
cv2.imwrite("out/roi_preview.png", crop)
print("saved out/roi_preview.png")