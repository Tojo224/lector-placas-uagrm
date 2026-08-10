/**
 * Web Worker para el procesamiento de fotogramas en segundo plano.
 * 
 * Evita bloquear el hilo principal de la UI al realizar el cálculo de diferencia 
 * de pixeles para la detección de movimiento.
 */

class MotionDetector {
  constructor(threshold = 20, minPercent = 0.05) {
    this.threshold = threshold;
    this.minPercent = minPercent;
    this.prevBuffer = null;
  }

  detect(buffer) {
    const len = buffer.length;

    if (!this.prevBuffer || this.prevBuffer.length !== len) {
      this.prevBuffer = new Uint8ClampedArray(len);
      this.prevBuffer.set(buffer);
      return true;
    }

    let changedPixels = 0;
    let sampledPixels = 0;
    const step = 16;

    for (let i = 0; i < len; i += step) {
      const gray1 = 0.299 * buffer[i] + 0.587 * buffer[i + 1] + 0.114 * buffer[i + 2];
      const gray2 = 0.299 * this.prevBuffer[i] + 0.587 * this.prevBuffer[i + 1] + 0.114 * this.prevBuffer[i + 2];

      if (Math.abs(gray1 - gray2) > this.threshold) {
        changedPixels++;
      }
      sampledPixels++;
    }

    this.prevBuffer.set(buffer);
    const changeRatio = changedPixels / sampledPixels;
    return changeRatio >= this.minPercent;
  }
}

let detector = null;

self.onmessage = function (e) {
  const { type, payload } = e.data;

  if (type === "INIT") {
    detector = new MotionDetector(payload.threshold, payload.minPercent);
  } else if (type === "PROCESS") {
    if (!detector) {
      detector = new MotionDetector();
    }
    const { buffer } = payload;
    const hasMotion = detector.detect(buffer);
    // Devolvemos el resultado y el buffer (usando Transferable Objects para no copiar memoria)
    self.postMessage({ type: "RESULT", payload: { hasMotion, buffer } }, [buffer.buffer]);
  }
};
