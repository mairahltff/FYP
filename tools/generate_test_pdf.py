from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

BASE = r"C:\FYP\uploads\e2e-user"
os.makedirs(BASE, exist_ok=True)
PATH = os.path.join(BASE, "vector_control_test.pdf")

c = canvas.Canvas(PATH, pagesize=letter)
t = c.beginText(72, 720)
t.textLine("WHO report discusses vector control strategies.")
t.textLine("Vector control includes insecticide-treated nets and indoor residual spraying.")
c.drawText(t)
c.showPage()
c.save()
print("Wrote:", PATH)
