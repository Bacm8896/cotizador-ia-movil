"""Convierte el logo con fondo rojo cuadrado (assets/logo_fuente.png) en un logo transparente (assets/logo.png).

El fondo es un degradado rojo oscuro; se elimina rellenando desde los bordes con tolerancia local
(el degradado cambia suavemente, los contornos del dibujo no). El texto blanco pasa a gris oscuro
para que se lea sobre papel blanco. Uso:  python scripts/preparar_logo.py
"""
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "assets" / "logo_fuente.png"
SALIDA = RAIZ / "assets" / "logo.png"
TOLERANCIA = 7        # cambio máximo entre píxeles vecinos que aún cuenta como fondo
FILA_TEXTO = 0.60     # el texto "ALARMEC" está en la parte inferior del logo
TINTA = (28, 28, 28)  # color del texto sobre papel blanco


def main() -> None:
    bgr = cv2.imread(str(FUENTE), cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    suavizado = cv2.GaussianBlur(bgr, (3, 3), 0)
    # solo puede ser fondo un píxel rojizo (el contorno negro de la cámara no lo es, aunque sea oscuro)
    b, g, r = (suavizado[..., i].astype(int) for i in range(3))
    rojizo = (r - np.maximum(g, b)) > 22
    suavizado[~rojizo] = (0, 255, 0)  # barrera: el relleno no atraviesa lo que no es rojizo

    # 1) fondo = región conectada al borde cuyo color cambia suavemente
    mascara = np.zeros((h + 2, w + 2), np.uint8)
    tol = (TOLERANCIA,) * 3
    semillas = [(x, 0) for x in range(0, w, 25)] + [(x, h - 1) for x in range(0, w, 25)] + \
               [(0, y) for y in range(0, h, 25)] + [(w - 1, y) for y in range(0, h, 25)]
    for sx, sy in semillas:
        if mascara[sy + 1, sx + 1] == 0:
            cv2.floodFill(suavizado.copy(), mascara, (sx, sy), 0, tol, tol, cv2.FLOODFILL_MASK_ONLY | 4 | (255 << 8))
    fondo = mascara[1:-1, 1:-1] > 0

    # 2) los huecos pequeños de fondo dentro del dibujo no se tocan; se suaviza el borde del recorte
    alfa = np.where(fondo, 0, 255).astype(np.uint8)
    alfa = cv2.morphologyEx(alfa, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))   # quita motas sueltas
    alfa = cv2.GaussianBlur(alfa, (3, 3), 0)

    # 3) texto claro de la parte inferior -> tinta oscura (sobre papel blanco no se vería)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    claridad = rgb.min(axis=2)
    zona = np.zeros((h, w), bool)
    zona[int(h * FILA_TEXTO):, :] = True
    es_texto = zona & (alfa > 0) & (claridad > 90)
    peso = np.clip((claridad - 90) / 110.0, 0, 1) * es_texto  # antialias: más claro = más tinta
    for c, valor in enumerate(TINTA):
        rgb[..., c] = rgb[..., c] * (1 - peso) + valor * peso

    # 4) recorte al contenido con un pequeño margen
    ys, xs = np.where(alfa > 40)
    m = 12
    y0, y1, x0, x1 = max(ys.min() - m, 0), min(ys.max() + m, h), max(xs.min() - m, 0), min(xs.max() + m, w)
    rgba = np.dstack([rgb, alfa.astype(np.float32)])[y0:y1, x0:x1].clip(0, 255).astype(np.uint8)
    cv2.imwrite(str(SALIDA), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    print(f"Logo transparente: {SALIDA.name} {rgba.shape[1]}x{rgba.shape[0]}")


if __name__ == "__main__":
    main()
