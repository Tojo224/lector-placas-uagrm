/**
 * Módulo de detección de movimiento ultra-rápido por software.
 * 
 * Compara dos fotogramas sucesivos calculando la diferencia de luminancia
 * en una rejilla de submuestreo para optimizar el rendimiento.
 */
export class MotionDetector {
  /**
   * @param {number} threshold Umbral de diferencia de luminosidad por píxel (0-255)
   * @param {number} minPercent Porcentaje mínimo de píxeles cambiados para detectar movimiento
   */
  constructor(threshold = 20, minPercent = 0.05) {
    this.threshold = threshold;
    this.minPercent = minPercent;
    this.prevBuffer = null;
  }

  /**
   * Compara el fotograma actual con el anterior.
   * 
   * @param {ImageData} imageData Datos de imagen del canvas
   * @returns {boolean} True si se detecta movimiento significativo, False si está estático
   */
  detect(imageData) {
    const data = imageData.data;
    const len = data.length;

    if (!this.prevBuffer || this.prevBuffer.length !== len) {
      this.prevBuffer = new Uint8ClampedArray(len);
      this.prevBuffer.set(data);
      return true; // Procesar el primer fotograma por defecto
    }

    let changedPixels = 0;
    let sampledPixels = 0;

    // Submuestreo: iteramos saltando píxeles (de 16 en 16 bytes = 4 píxeles) 
    // para acelerar el cálculo exponencialmente.
    const step = 16;
    for (let i = 0; i < len; i += step) {
      // Luminancia estándar (ITU-R BT.601)
      const gray1 = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      const gray2 = 0.299 * this.prevBuffer[i] + 0.587 * this.prevBuffer[i + 1] + 0.114 * this.prevBuffer[i + 2];

      if (Math.abs(gray1 - gray2) > this.threshold) {
        changedPixels++;
      }
      sampledPixels++;
    }

    // Actualizar buffer previo
    this.prevBuffer.set(data);

    const changeRatio = changedPixels / sampledPixels;
    return changeRatio >= this.minPercent;
  }
}
