/**
 * Fusión inteligente de caracteres OCR para reconstrucción de placas.
 * 
 * Agrupa las lecturas recientes por su longitud (6 o 7 caracteres) y para cada posición
 * selecciona el carácter más frecuente y con mayor confianza.
 *
 * @param {Array<{text: string, confidence: number}>} reads Buffer de lecturas recientes
 * @returns {string|null} La placa reconstruida si tiene formato boliviano válido, de lo contrario null
 */
export function fuseOCRReads(reads) {
  if (!reads || reads.length === 0) return null;

  // Filtrar lecturas válidas y limpiar caracteres no permitidos
  const cleanReads = reads
    .map(r => ({
      text: (r.text || "").replace(/[^A-Z0-9]/gi, "").toUpperCase(),
      confidence: r.confidence || 0.0
    }))
    .filter(r => r.text.length === 6 || r.text.length === 7);

  if (cleanReads.length === 0) return null;

  // Agrupar por longitud para evitar desalineación posicional
  const lenGroups = {};
  cleanReads.forEach(r => {
    const len = r.text.length;
    if (!lenGroups[len]) lenGroups[len] = [];
    lenGroups[len].push(r);
  });

  // Elegir el grupo de longitud más representativo (más lecturas)
  const chosenLen = Object.keys(lenGroups).reduce((a, b) =>
    lenGroups[a].length >= lenGroups[b].length ? a : b
  );
  const group = lenGroups[chosenLen];
  const length = parseInt(chosenLen, 10);

  // Calcular el carácter más votado por posición
  let fused = "";
  for (let pos = 0; pos < length; pos++) {
    const freqs = {};
    group.forEach(r => {
      const char = r.text[pos];
      if (!char) return;
      if (!freqs[char]) freqs[char] = { count: 0, sumConf: 0 };
      freqs[char].count += 1;
      freqs[char].sumConf += r.confidence;
    });

    // Encontrar el carácter ganador de la posición por frecuencia y luego por confianza acumulada
    let bestChar = "";
    let maxVotes = -1;
    let maxConf = -1;

    Object.entries(freqs).forEach(([char, data]) => {
      if (
        data.count > maxVotes ||
        (data.count === maxVotes && data.sumConf > maxConf)
      ) {
        bestChar = char;
        maxVotes = data.count;
        maxConf = data.sumConf;
      }
    });

    fused += bestChar;
  }

  // Validar formato boliviano: 3-4 dígitos seguidos de 3 letras
  const pattern = /^\d{3,4}[A-Z]{3}$/;
  if (pattern.test(fused)) {
    return fused;
  }

  return null;
}
