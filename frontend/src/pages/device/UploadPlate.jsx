import { useEffect, useRef, useState } from "react";
import UploadImage from "../../components/UploadImage";
import { analyzeWithEdge, getEdgeHealth, getEdgeStatus, getEdgeVersion, uploadPlateImage } from "../../api/edge";
import { useAuth } from "../../hooks/useAuth";
import { formatPlate } from "../../utils/formatters";
import VehicleFoundModal from "../../components/UploadPlate/VehicleFoundModal";
import PlateNotFoundModal from "../../components/UploadPlate/PlateNotFoundModal";

import { fuseOCRReads } from "../../utils/ocrFusion";

const ownerInitialState = {
  code: "",
  full_name: "",
  document_id: "",
  role: "STUDENT",
  faculty: "",
  contact_info: "",
  status: "ACTIVE",
  is_active: true
};

const vehicleInitialState = {
  license_plate: "",
  brand: "",
  model: "",
  color: "",
  vehicle_type: "CAR",
  year: "",
  observation: ""
};

const unsupportedCentralOperation = async () => {
  throw new Error("Esta operación administrativa no está disponible en el scanner Edge local.");
};

function UploadPlate() {
  const { user } = useAuth();
  const isAdmin = user?.rol === "ADMINISTRATIVE" || user?.rol === "ADMINISTRADOR";
  const isStaff = user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR";
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const ipImageRef = useRef(null);
  const modelRef = useRef(null);
  const requestRef = useRef(null);
  const requestControllerRef = useRef(null);
  const detectionTimerRef = useRef(null);
  const readsHistoryRef = useRef([]);
  const workerRef = useRef(null);
  // Mapa de votos: texto_normalizado -> { count, bbox, score, text, lastFrameTs }
  const voteMapRef = useRef(new Map());
  const VOTES_NEEDED = 2; // OPT-D: 2 frames consecutivos — balance entre velocidad y anti-falsos-positivos

  const [modelLoading, setModelLoading] = useState(false);
  const [trackingBoxes, setTrackingBoxes] = useState([]);
  const [fileName, setFileName] = useState("");
  const [manualPlate, setManualPlate] = useState("");
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [lookupResult, setLookupResult] = useState(null);
  const [showFoundModal, setShowFoundModal] = useState(false);
  const [showRegistrationModal, setShowRegistrationModal] = useState(false);
  const [registeringForAnotherPerson, setRegisteringForAnotherPerson] = useState(false);
  const [registerError, setRegisterError] = useState("");
  const [registerSuccess, setRegisterSuccess] = useState("");
  const [vehicleForm, setVehicleForm] = useState(vehicleInitialState);
  const [ownerForm, setOwnerForm] = useState(ownerInitialState);
  const [vehiclePhoto, setVehiclePhoto] = useState(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [availableCameras, setAvailableCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [cameraSourceType, setCameraSourceType] = useState("local"); // "local" | "ip"
  const [ipCameraUrl, setIpCameraUrl] = useState("");
  const [accessZone, setAccessZone] = useState("Portería Principal");
  const [accessNotes, setAccessNotes] = useState("");
  const [accessSuccess, setAccessSuccess] = useState("");
  const [accessError, setAccessError] = useState("");
  const [autoAccessLog, setAutoAccessLog] = useState(null);
  const [registeringAccess, setRegisteringAccess] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [analysisPreview, setAnalysisPreview] = useState(null);
  const [scanError, setScanError] = useState("");
  const [activeTab, setActiveTab] = useState(user?.rol === "DISPOSITIVO" ? "camera" : null); // null | "image" | "camera"
  const [activeModal, setActiveModal] = useState(null); // null | "file" | "snapshot"
  const [edgeState, setEdgeState] = useState({ connected: false, health: null, status: null, version: null });
  const [decisionReason, setDecisionReason] = useState("");
  const activeModalRef = useRef(null);
  const edgeConnectedRef = useRef(false);

  useEffect(() => {
    // Inicializar el Web Worker para detección de movimiento en segundo plano
    workerRef.current = new Worker(
      new URL("../../utils/cameraWorker.js", import.meta.url),
      { type: "module" }
    );

    // Configurar parámetros de detección de movimiento
    workerRef.current.postMessage({
      type: "INIT",
      payload: { threshold: 20, minPercent: 0.05 }
    });

    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  useEffect(() => {
    activeModalRef.current = activeModal;
  }, [activeModal]);

  useEffect(() => {
    let active = true;
    const refreshEdgeState = async () => {
      const [health, status, version] = await Promise.allSettled([
        getEdgeHealth(), getEdgeStatus(), getEdgeVersion()
      ]);
      if (!active) return;
      setEdgeState({
        connected: health.status === "fulfilled" && status.status === "fulfilled",
        health: health.status === "fulfilled" ? health.value : null,
        status: status.status === "fulfilled" ? status.value : null,
        version: version.status === "fulfilled" ? version.value : null
      });
    };
    refreshEdgeState();
    const timer = setInterval(refreshEdgeState, 5000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  useEffect(() => {
    edgeConnectedRef.current = edgeState.connected;
  }, [edgeState.connected]);

  useEffect(() => {
    if (!navigator.mediaDevices?.addEventListener) return undefined;
    const handleDeviceChange = () => refreshCameraList().catch(() => {});
    navigator.mediaDevices.addEventListener("devicechange", handleDeviceChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", handleDeviceChange);
  }, []);

  useEffect(() => {
    // La cámara siempre encendida mientras estemos en la pestaña de cámara
    if (activeTab === "camera") {
      startCamera(true);
    } else if (activeModal === "snapshot") {
      startCamera(false);
    } else {
      stopCamera();
    }
    return () => {
      // Siempre detener el stream al re-ejecutar el efecto para evitar acumulación de streams
      stopCamera();
    };
  }, [activeTab, activeModal, cameraSourceType]);

  const resetLookupState = () => {
    setLookupError("");
    setLookupResult(null);
    setRegisterSuccess("");
    setRegisterError("");
    setAnalysisPreview(null);
    setShowFoundModal(false);
    setAutoAccessLog(null);
  };

  const openFoundModal = (result) => {
    setLookupResult(result);
    setShowFoundModal(true);
    setShowRegistrationModal(false);
    setAccessSuccess("");
    setAccessError("");
    setAccessNotes("");
  };

  const openRegistrationModal = (plateValue) => {
    setShowRegistrationModal(true);
    setShowFoundModal(false);
    setVehicleForm((current) => ({
      ...current,
      license_plate: plateValue || current.license_plate
    }));
  };

  const handleLookupPlate = async (plateValue, evidence = null, analysisResult = null) => {
    resetLookupState();
    setLookupLoading(true);

    if (!analysisResult) {
      setLookupError("Se requiere una imagen analizada por el Edge Agent para continuar.");
      setLookupLoading(false);
      return;
    }
    setDecisionReason(analysisResult.motivo || "");
    if (analysisResult.decision === "DUPLICATE") {
      setLookupLoading(false);
      return;
    }
    if (analysisResult.decision === "ALLOW" && analysisResult.es_registrado) {
      const result = {
        id: analysisResult.vehiculo_id,
        license_plate: analysisResult.placa_normalizada || plateValue,
        propietario: { nombre: analysisResult.propietario_nombre || "Propietario" }
      };
      setLookupResult(result);
      setAutoAccessLog({
        id: analysisResult.acceso_id,
        direction: analysisResult.tipo_acceso === "ENTRADA" ? "ENTRY" : "EXIT",
        zone: "Portería Principal",
        timestamp: new Date().toISOString(),
        vehiculo_id: analysisResult.vehiculo_id,
        media_status: analysisResult.media_estado
      });
      setActiveModal("access_confirmed");
      setTimeout(() => {
        setActiveModal(null);
        setLookupResult(null);
        setAutoAccessLog(null);
        setManualPlate("");
      }, 5000);
    } else {
      // Placa desconocida o denegada por el Edge Agent — enviar al servidor central
      // para crear o reutilizar una SolicitudRegistroVehiculo.
      setManualPlate(plateValue);
      if (evidence) {
        try {
          const form = new FormData();
          form.append("file", evidence, "vehiculo-desconocido.jpg");
          if (plateValue) {
            form.append("placa_sugerida", plateValue.replace("-", "").replace(" ", "").toUpperCase().trim());
          }
          const centralResult = await uploadPlateImage(form);
          // Mostrar modal de solicitud si el backend procesó la imagen,
          // tanto si crea una nueva solicitud como si ya existía una pendiente.
          if (centralResult && (centralResult.solicitud_id || centralResult.placa_detectada)) {
            setAnalysisPreview(centralResult);
            setActiveModal("plate_request_sent");
            setLookupLoading(false);
            return;
          }
        } catch (centralError) {
          const status = centralError?.response?.status;
          if (status === 401 || status === 403) {
            setLookupError("Sesión expirada o sin permisos. Por favor inicia sesión de nuevo.");
            setLookupLoading(false);
            return;
          }
          // Error de red o del servidor — registrar pero continuar mostrando
          // el modal de placa no encontrada para no bloquear el flujo.
          console.warn("No se pudo enviar la solicitud al servidor central:", centralError?.response?.data?.detail || centralError?.message);
        }
      }
      setActiveModal("plate_not_found");
    }
    setLookupLoading(false);
    return;

    // Si el backend ya registró el acceso durante el análisis, no necesitamos
    // crear otro acceso — solo buscar los datos del vehículo para la UI.
    const backendAlreadyRegistered = Boolean(analysisResult?.acceso_id);

    try {
      let result = null;
      if (analysisResult) {
        if (!analysisResult.es_registrado) {
          // Si no está registrado en el backend, lanzar error ficticio 404 para entrar al bloque catch
          const err = new Error("Vehículo no registrado");
          err.response = { status: 404 };
          throw err;
        }
        // Sintetizar el resultado del vehículo sin hacer la petición protegida
        result = {
          id: analysisResult.vehiculo_id,
          license_plate: analysisResult.placa_normalizada || plateValue,
          propietario: {
            nombre: analysisResult.propietario_nombre || "Propietario",
            apellido_paterno: ""
          }
        };
      } else {
        result = await unsupportedCentralOperation(plateValue);
      }
      setLookupResult(result);
      
      if (analysisResult) {
        // En flujo de cámara en vivo (análisis automático), el backend ya gestiona el acceso
        // y el cooldown. Siempre mostramos confirmación visual de forma automática y transparente.
        const tipoAcceso = analysisResult.tipo_acceso || "ENTRADA";
        setAutoAccessLog({
          id: analysisResult.acceso_id || "cooldown-suppressed",
          direction: tipoAcceso === "ENTRADA" ? "ENTRY" : "EXIT",
          zone: "Portería Principal",
          timestamp: new Date().toISOString(),
          vehiculo_id: analysisResult.vehiculo_id,
        });
        setActiveModal("access_confirmed");
        setTimeout(() => {
          setActiveModal(null);
          setLookupResult(null);
          setAutoAccessLog(null);
          setManualPlate("");
        }, 5000);
      } else if (backendAlreadyRegistered) {
        // Fallback de seguridad
        const tipoAcceso = analysisResult.tipo_acceso || "ENTRADA";
        setAutoAccessLog({
          id: analysisResult.acceso_id,
          direction: tipoAcceso === "ENTRADA" ? "ENTRY" : "EXIT",
          zone: "Portería Principal",
          timestamp: new Date().toISOString(),
          vehiculo_id: analysisResult.vehiculo_id,
        });
        setActiveModal("access_confirmed");
        setTimeout(() => {
          setActiveModal(null);
          setLookupResult(null);
          setAutoAccessLog(null);
          setManualPlate("");
        }, 5000);
      } else {
        // Flujo manual o de imagen estática → registrar acceso ahora
        try {
          const autoResult = evidence
            ? await unsupportedCentralOperation({
                vehicle_id: result.id,
                zone: accessZone,
                notes: ""
              }, evidence)
            : await unsupportedCentralOperation({
            vehicle_id: result.id,
            zone: accessZone,
            notes: ""
          });
          const autoLog = autoResult.access || autoResult;
          if (autoResult.image_status) autoLog.image_status = autoResult.image_status;
          setAutoAccessLog(autoLog);
          setActiveModal("access_confirmed");
          
          setTimeout(() => {
            setActiveModal(null);
            setLookupResult(null);
            setAutoAccessLog(null);
            setManualPlate("");
          }, 5000);
          
        } catch (autoErr) {
          setAccessError(
            autoErr?.response?.data?.detail || autoErr.mensaje || "No se pudo auto-registrar el acceso."
          );
          setActiveModal("ingreso_egreso");
        }
      }
      
    } catch (error) {
      const status = error?.response?.status;
      if (status === 401) {
        // Token expirado: si el backend ya registró el acceso, aún mostramos confirmación
        if (backendAlreadyRegistered) {
          const tipoAcceso = analysisResult.tipo_acceso || "ENTRADA";
          setAutoAccessLog({
            id: analysisResult.acceso_id,
            direction: tipoAcceso === "ENTRADA" ? "ENTRY" : "EXIT",
            zone: "Portería Principal",
            timestamp: new Date().toISOString(),
            vehiculo_id: analysisResult.vehiculo_id,
          });
          setActiveModal("access_confirmed");
          setTimeout(() => {
            setActiveModal(null);
            setLookupResult(null);
            setAutoAccessLog(null);
            setManualPlate("");
          }, 5000);
        } else {
          setLookupError("Sesión expirada. Por favor inicia sesión de nuevo.");
        }
      } else if (status === 404) {
        if (evidence && !analysisResult?.solicitud_id) {
          try {
            const form = new FormData();
            form.append("file", evidence, "unknown-vehicle.jpg");
            analysisResult = await analyzeWithEdge(form);
          } catch (requestError) {
            setLookupError(requestError?.response?.data?.detail || "No se pudo enviar la solicitud de revisión.");
            return;
          }
        }
        if (analysisResult?.solicitud_id) {
          setManualPlate(plateValue);
          setActiveModal("plate_request_sent");
          return;
        }
        // Placa no registrada → informar al usuario
        setManualPlate(plateValue);
        setActiveModal("plate_not_found");
      } else {
        setLookupError(
          error?.response?.data?.detail || "Error al consultar la placa. Intenta de nuevo."
        );
      }
    } finally {
      setLookupLoading(false);
    }
  };

  const handleLookup = async (event) => {
    event.preventDefault();
    setLookupError("La decisión offline requiere una imagen analizada por el Edge Agent.");
  };

  const handleImageSelected = async (event) => {
    const file = event.target.files?.[0];
    setFileName(file ? file.name : "");
    if (!file) {
      return;
    }

    const ALLOWED_TYPES = ["image/jpeg", "image/png"];
    if (!ALLOWED_TYPES.includes(file.type)) {
      setLookupError("Formato no permitido. Por favor selecciona una imagen JPG o PNG.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLookupLoading(true);
      resetLookupState();
      const analysis = await analyzeWithEdge(formData);
      setAnalysisPreview(analysis);

      if (analysis?.placa_normalizada) {
        // OCR exitoso con formato boliviano confirmado
        setManualPlate(analysis.placa_normalizada);
        await handleLookupPlate(analysis.placa_normalizada, file, analysis);
      } else if (analysis?.placa_detectada) {
        // OCR detectó texto pero con baja confianza o formato inválido.
        // Intentar igualmente enviar al servidor central para que re-analice.
        const rawClean = analysis.placa_detectada.replace(/[^A-Z0-9]/gi, "").toUpperCase();
        setManualPlate(rawClean);
        await handleLookupPlate(rawClean, file, analysis);
      } else {
        setLookupError(analysis?.mensaje || "No se pudo detectar una placa en la imagen.");
      }
    } catch (error) {
      setLookupError(error?.response?.data?.detail || "No se pudo analizar la imagen. Intenta de nuevo.");
    } finally {
      setLookupLoading(false);
    }
  };

  useEffect(() => {
    if (cameraOpen && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [cameraOpen]);

  const detectFrame = async () => {
    const isIpMode = cameraSourceType === "ip";
    if (isIpMode) {
      if (!ipImageRef.current || !canvasRef.current || !cameraOpen) return;
    } else {
      if (!videoRef.current || !canvasRef.current || !streamRef.current) return;
    }
    if (!edgeConnectedRef.current) {
      setScanError("Edge Agent desconectado. Esperando reconexión...");
      detectionTimerRef.current = setTimeout(detectFrame, 2000);
      return;
    }

    // Si hay un modal activo en pantalla, pausar el análisis OCR para no saturar la CPU,
    // pero mantener la cámara encendida.
    if (activeModalRef.current !== null) {
      requestRef.current = null;
      if (isIpMode ? cameraOpen : streamRef.current) detectionTimerRef.current = setTimeout(detectFrame, 1000);
      return;
    }

    if (requestRef.current === "processing") return;

    requestRef.current = "processing";
    const canvas = canvasRef.current;

    // Conserva caracteres de placas lejanas sin enviar el fotograma 1080p completo.
    const MAX_DETECTION_DIM = 960;
    const sourceEl = isIpMode ? ipImageRef.current : videoRef.current;
    let videoW = isIpMode ? sourceEl.naturalWidth : sourceEl.videoWidth;
    let videoH = isIpMode ? sourceEl.naturalHeight : sourceEl.videoHeight;

    if (videoW === 0 || !videoW) {
      requestRef.current = null;
      if (isIpMode ? cameraOpen : streamRef.current) detectionTimerRef.current = setTimeout(detectFrame, 1000);
      return;
    }

    if (videoW > MAX_DETECTION_DIM || videoH > MAX_DETECTION_DIM) {
      if (videoW > videoH) {
        videoH = Math.round((videoH * MAX_DETECTION_DIM) / videoW);
        videoW = MAX_DETECTION_DIM;
      } else {
        videoW = Math.round((videoW * MAX_DETECTION_DIM) / videoH);
        videoH = MAX_DETECTION_DIM;
      }
    }

    canvas.width = videoW;
    canvas.height = videoH;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(sourceEl, 0, 0, canvas.width, canvas.height);

    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    let nextInterval = 250;

    try {
      // --- Detección de Movimiento por Web Worker ---
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const buffer = imageData.data;

      const hasMotion = await new Promise((resolve) => {
        const handleMessage = (e) => {
          if (e.data.type === "RESULT") {
            workerRef.current.removeEventListener("message", handleMessage);
            resolve(e.data.payload.hasMotion);
          }
        };
        workerRef.current.addEventListener("message", handleMessage);
        workerRef.current.postMessage({ type: "PROCESS", payload: { buffer } }, [buffer.buffer]);
      });

      if (!hasMotion) {
        requestRef.current = null;
        clearTimeout(timeoutId);
        if (requestControllerRef.current === controller) {
          requestControllerRef.current = null;
        }
        setScanError("");
        setTrackingBoxes([]);
        if (streamRef.current) {
          detectionTimerRef.current = setTimeout(detectFrame, 800); // 800ms de espera si está estático
        }
        return;
      }

      // --- Envío del fotograma al Edge Agent ---
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.90));
      if (blob) {
        const formData = new FormData();
        formData.append("file", blob, "frame.jpg");
        const analysis = await analyzeWithEdge(formData, true, controller.signal, false);

        const normalizedText = analysis.placa_normalizada
          ? analysis.placa_normalizada
          : (analysis.placa_detectada
              ? analysis.placa_detectada.replace(/[^A-Z0-9]/gi, "").toUpperCase()
              : null);

        const voteMap = voteMapRef.current;
        const now = Date.now();

        if (normalizedText && normalizedText.length >= 4) {
          // Guardar en el historial de lecturas recientes (máximo 5)
          const readsHistory = readsHistoryRef.current;
          readsHistory.push({ text: normalizedText, confidence: analysis.confianza });
          if (readsHistory.length > 5) {
            readsHistory.shift();
          }

          // Intentar fusionar las lecturas del historial
          const fusedPlate = fuseOCRReads(readsHistory);

          // Sumar voto para el tracking visual en pantalla
          const existing = voteMap.get(normalizedText);
          const newCount = existing ? existing.count + 1 : 1;
          voteMap.set(normalizedText, {
            count: newCount,
            bbox: analysis.plate_bbox,
            score: analysis.confianza,
            text: analysis.placa_detectada,
            isValidFormat: analysis.es_formato_valido,
            lastFrameTs: now,
          });

          // Limpiar textos antiguos del mapa de votos
          for (const [key, val] of voteMap.entries()) {
            if (key !== normalizedText && now - val.lastFrameTs > 4000) {
              voteMap.delete(key);
            }
          }

          // Ganador: si la fusión nos da una placa válida, o si un frame tiene altísima confianza y formato válido
          const isWinner = fusedPlate || (analysis.es_formato_valido && analysis.confianza >= 0.88);

          if (isWinner) {
            const finalPlate = fusedPlate || normalizedText;
            const evidenceCanvas = document.createElement("canvas");
            evidenceCanvas.width = videoRef.current.videoWidth || canvas.width;
            evidenceCanvas.height = videoRef.current.videoHeight || canvas.height;
            evidenceCanvas.getContext("2d").drawImage(
              videoRef.current,
              0,
              0,
              evidenceCanvas.width,
              evidenceCanvas.height
            );
            const evidenceBlob = await new Promise((resolve) =>
              evidenceCanvas.toBlob(resolve, "image/jpeg", 0.92)
            );
            voteMap.clear();
            readsHistoryRef.current = [];
            setTrackingBoxes([]);
            setAnalysisPreview(analysis);
            setManualPlate(finalPlate);
            const confirmedForm = new FormData();
            confirmedForm.append("file", evidenceBlob || blob, "evidence.jpg");
            const confirmed = await analyzeWithEdge(confirmedForm, false, controller.signal, true);
            setAnalysisPreview(confirmed);
            handleLookupPlate(finalPlate, evidenceBlob || blob, confirmed);
            return;
          }

          // Mostrar cajas de seguimiento en la UI
          let newBoxes = [];
          if (analysis.raw_bboxes && analysis.raw_bboxes.length > 0) {
            newBoxes = analysis.raw_bboxes.map(bbox => {
              const [x1, y1, x2, y2] = bbox;
              return { bbox: [x1, y1, x2 - x1, y2 - y1], type: 'raw' };
            });
          }
          if (analysis.plate_bbox) {
            const [x1, y1, x2, y2] = analysis.plate_bbox;
            const entry = voteMap.get(normalizedText);
            newBoxes.push({
              bbox: [x1, y1, x2 - x1, y2 - y1],
              score: analysis.confianza,
              text: fusedPlate || analysis.placa_normalizada || analysis.placa_detectada,
              votes: entry ? entry.count : 1,
              votesNeeded: VOTES_NEEDED,
              type: 'plate-voting',
            });
          }
          setScanError("");
          setTrackingBoxes(newBoxes);
          nextInterval = 500;

        } else {
          // Sin texto válido: limpiar votos antiguos
          for (const [key, val] of voteMap.entries()) {
            if (now - val.lastFrameTs > 3000) voteMap.delete(key);
          }
          setScanError("");
          setTrackingBoxes([]);
          nextInterval = 250;
        }
      }
    } catch (e) {
      if (e.name !== "AbortError" && e.code !== "ERR_CANCELED") {
        console.error("Error en detectFrame:", e);
        setScanError(e.response?.data?.detail || e.mensaje || "Error al procesar el fotograma. Reintentando...");
        setTrackingBoxes([]);
      }
    } finally {
      clearTimeout(timeoutId);
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
    requestRef.current = null;
    if (cameraSourceType === "ip" ? cameraOpen : streamRef.current) {
      detectionTimerRef.current = setTimeout(detectFrame, nextInterval);
    }
  };

  const refreshCameraList = async () => {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter((device) => device.kind === "videoinput");
    setAvailableCameras(cameras);
    return cameras;
  };

  const startCamera = async (isLive = false, cameraId = selectedCameraId) => {
    // Si ya hay un stream activo, detenerlo antes de pedir uno nuevo
    if (streamRef.current) {
      stopCamera();
    }
    if (cameraSourceType === "ip") {
      setCameraError("");
      setCameraOpen(true);
      if (isLive) {
        detectionTimerRef.current = setTimeout(detectFrame, 300);
      }
      return;
    }
    try {
      setCameraError("");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          ...(cameraId
            ? { deviceId: { exact: cameraId } }
            : { facingMode: { ideal: "environment" } }),
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30, min: 24 }
        },
        audio: false
      });
      const [videoTrack] = stream.getVideoTracks();
      const capabilities = videoTrack?.getCapabilities?.() || {};
      const advanced = {};
      if (Array.isArray(capabilities.focusMode) && capabilities.focusMode.includes("continuous")) {
        advanced.focusMode = "continuous";
      }
      if (Array.isArray(capabilities.exposureMode) && capabilities.exposureMode.includes("continuous")) {
        advanced.exposureMode = "continuous";
      }
      if (Object.keys(advanced).length > 0) {
        videoTrack.applyConstraints({ advanced: [advanced] }).catch(() => {});
      }
      streamRef.current = stream;
      const activeCameraId = videoTrack?.getSettings?.().deviceId || cameraId;
      if (activeCameraId) setSelectedCameraId(activeCameraId);
      await refreshCameraList();
      setCameraOpen(true);
      
      if (isLive) {
        // Iniciar bucle con throttle (no requestAnimationFrame)
        detectionTimerRef.current = setTimeout(detectFrame, 300);
      }
      
    } catch (error) {
      const msg = error?.name === "NotAllowedError"
        ? "Permiso de cámara denegado. Habilita el acceso en la configuración del navegador."
        : error?.name === "NotFoundError"
          ? "No se encontró ninguna cámara disponible. Verifica la conexión del dispositivo."
          : "No se pudo abrir la cámara. Verifica que no esté siendo usada por otra aplicación.";
      setCameraError(msg);
      console.error("Error al abrir cámara:", error);
    }
  };

  const stopCamera = () => {
    clearTimeout(detectionTimerRef.current);
    detectionTimerRef.current = null;
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCameraOpen(false);
    setTrackingBoxes([]);
    requestRef.current = null;
    voteMapRef.current.clear(); // Limpiar votos acumulados al cerrar
  };

  const changeCamera = async (event) => {
    const cameraId = event.target.value;
    setSelectedCameraId(cameraId);
    stopCamera();
    await startCamera(activeTab === "camera", cameraId);
  };

  const captureFromCamera = async () => {
    const isIpMode = cameraSourceType === "ip";
    const sourceEl = isIpMode ? ipImageRef.current : videoRef.current;
    if (!sourceEl || !canvasRef.current) {
      return;
    }

    const canvas = canvasRef.current;
    canvas.width = isIpMode ? sourceEl.naturalWidth : sourceEl.videoWidth;
    canvas.height = isIpMode ? sourceEl.naturalHeight : sourceEl.videoHeight;
    const context = canvas.getContext("2d");
    context.drawImage(sourceEl, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) {
      setCameraError("No se pudo capturar la imagen desde la camara.");
      return;
    }

    const formData = new FormData();
    formData.append("file", blob, "captura-placa.jpg");

    try {
      setLookupLoading(true);
      const analysis = await analyzeWithEdge(formData);
      setAnalysisPreview(analysis);
      if (analysis?.placa_normalizada) {
        setManualPlate(analysis.placa_normalizada);
        await handleLookupPlate(analysis.placa_normalizada, blob, analysis);
      } else {
        setLookupError(analysis?.mensaje || "No se pudo detectar una placa en la captura.");
      }
    } catch (error) {
      setLookupError(error?.response?.data?.detail || "Error al analizar la captura de la cámara. Intenta de nuevo.");
    } finally {
      setLookupLoading(false);
      stopCamera();
    }
  };

  const handleVehicleSubmit = async (event) => {
    event.preventDefault();
    setRegisterError("El registro de vehículos pertenece al backend central y no está disponible en el scanner local.");
    return;
    setRegisterError("");
    setRegisterSuccess("");

    try {
      const payload = {
        ...vehicleForm,
        license_plate: formatPlate(vehicleForm.license_plate),
        registered_by_user_id: user?.id,
        owner: ownerForm
      };

      const createdVehicle = await unsupportedCentralOperation(payload);
      setLookupResult(createdVehicle);
      setRegisterSuccess("Vehiculo registrado correctamente.");
      setVehicleForm(vehicleInitialState);
      setOwnerForm(ownerInitialState);
      setVehiclePhoto(null);
      setManualPlate(createdVehicle.license_plate);
      setShowRegistrationModal(false);
      setShowFoundModal(true);
      setAccessSuccess("");
      setAccessError("");
      setAccessNotes("");
    } catch (error) {
      setRegisterError(error.mensaje || "Error al guardar el vehiculo.");
    }
  };

  const handleRegisterAccess = async (direction) => {
    setAccessError("La dirección y la decisión ya fueron determinadas por el Edge Agent.");
    return;
    if (!lookupResult?.id) return;
    try {
      setRegisteringAccess(true);
      setAccessError("");
      const log = await unsupportedCentralOperation({
        vehicle_id: lookupResult.id,
        direction: direction,
        zone: accessZone,
        notes: accessNotes
      });
      // Pasar a modal de confirmación y cerrar automáticamente en 4s
      setActiveModal("access_confirmed");
      setAutoAccessLog(log);
      setTimeout(() => {
        setActiveModal(null);
        setLookupResult(null);
        setAutoAccessLog(null);
        setManualPlate("");
      }, 4000);
    } catch (err) {
      setAccessError(
        err?.response?.data?.detail || err.mensaje || "No se pudo registrar el acceso."
      );
    } finally {
      setRegisteringAccess(false);
    }
  };

  const registrationTitle = isAdmin && registeringForAnotherPerson
    ? "Registrar vehiculo de otra persona"
    : "Registrar mi vehiculo";

  return (
    <section className="page-stack">
      <div className="card" data-testid="edge-operational-status" style={{ padding: "0.9rem 1.1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
          <div>
            <strong style={{ color: edgeState.connected ? "#15803d" : "#b91c1c" }}>
              {edgeState.connected ? "Edge Agent conectado" : "Edge Agent desconectado"}
            </strong>
            <span className="muted-text" style={{ marginLeft: "0.75rem" }}>
              OCR {edgeState.health?.lifecycle_state === "INITIALIZING_OCR" ? "inicializando" : edgeState.health?.ocr_ready ? "listo" : "no listo"}
            </span>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <span>{edgeState.status?.sync?.network === "online" ? "ONLINE" : "OFFLINE"}</span>
            <span>Caché: {edgeState.status?.cache?.state || "desconocido"}</span>
            <span>Versión: {edgeState.version?.version || "—"}</span>
          </div>
        </div>
        {!edgeState.connected && (
          <p className="error-text" style={{ margin: "0.6rem 0 0" }}>
            El scanner local no está disponible. No existe fallback hacia Railway o Neon.
          </p>
        )}
        {edgeState.connected && edgeState.status?.provisioned === false && (
          <p className="error-text" style={{ margin: "0.6rem 0 0" }}>
            Esta instalación aún no está provisionada. <a href="/configuracion"><u>Abrir configuración inicial</u></a>.
          </p>
        )}
        {edgeState.connected && edgeState.status?.sync?.network !== "online" && (
          <p className="muted-text" style={{ margin: "0.6rem 0 0" }}>
            Operación local disponible; la sincronización continuará cuando vuelva Internet.
          </p>
        )}
        <details style={{ marginTop: "0.6rem" }}>
          <summary>Detalles operativos</summary>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.35rem 1rem", marginTop: "0.5rem" }}>
            <span>Edad snapshot: {edgeState.status?.cache?.age_hours ?? "—"} h</span>
            <span>Eventos pendientes: {edgeState.status?.sync?.pending ?? 0}</span>
            <span>Eventos retry: {edgeState.status?.sync?.retry ?? 0}</span>
            <span>Dead letters: {edgeState.status?.sync?.dead_letters ?? 0}</span>
            <span>Evidencias pendientes: {(edgeState.status?.media?.pending ?? 0) + (edgeState.status?.media?.retry ?? 0)}</span>
            <span>Poco espacio: {edgeState.status?.media?.low_space ? "Sí" : "No"}</span>
          </div>
        </details>
      </div>
      {activeTab === null && (
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "35vh",
          padding: "1rem"
        }}>
          <h2 style={{ color: "var(--color-primary)", marginBottom: "0.25rem", fontSize: "1.4rem", textAlign: "center" }}>
            Selecciona una opción
          </h2>
          <p className="muted-text" style={{ marginBottom: "1.5rem", fontSize: "0.9rem", textAlign: "center" }}>
            Elige el método de detección de placas para comenzar el control de acceso
          </p>

          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: "1.25rem",
            width: "100%",
            maxWidth: "600px"
          }}>
            <button
              type="button"
              onClick={() => { setActiveTab("image"); setActiveModal("file"); resetLookupState(); }}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "1.5rem 1.25rem",
                borderRadius: "12px",
                border: "2px solid rgba(21, 62, 117, 0.15)",
                background: "white",
                color: "var(--color-primary)",
                cursor: "pointer",
                transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                boxShadow: "0 6px 15px rgba(21, 62, 117, 0.04)"
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-3px)";
                e.currentTarget.style.borderColor = "var(--color-primary)";
                e.currentTarget.style.background = "#f8fafc";
                e.currentTarget.style.boxShadow = "0 10px 20px rgba(21, 62, 117, 0.08)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.borderColor = "rgba(21, 62, 117, 0.15)";
                e.currentTarget.style.background = "white";
                e.currentTarget.style.boxShadow = "0 6px 15px rgba(21, 62, 117, 0.04)";
              }}
            >
              <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-primary)", marginBottom: "0.85rem" }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span style={{ fontSize: "1.1rem", fontWeight: "bold", marginBottom: "0.35rem" }}>
                Subir Imagen de Placa
              </span>
              <span style={{ fontSize: "0.82rem", color: "#6b7280", textAlign: "center", lineHeight: "1.4" }}>
                Carga un archivo local o toma una fotografía instantánea
              </span>
            </button>

            <button
              type="button"
              onClick={() => { setActiveTab("camera"); resetLookupState(); }}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "1.5rem 1.25rem",
                borderRadius: "12px",
                border: "2px solid rgba(21, 62, 117, 0.15)",
                background: "white",
                color: "var(--color-primary)",
                cursor: "pointer",
                transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                boxShadow: "0 6px 15px rgba(21, 62, 117, 0.04)"
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-3px)";
                e.currentTarget.style.borderColor = "var(--color-primary)";
                e.currentTarget.style.background = "#f8fafc";
                e.currentTarget.style.boxShadow = "0 10px 20px rgba(21, 62, 117, 0.08)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.borderColor = "rgba(21, 62, 117, 0.15)";
                e.currentTarget.style.background = "white";
                e.currentTarget.style.boxShadow = "0 6px 15px rgba(21, 62, 117, 0.04)";
              }}
            >
              <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-primary)", marginBottom: "0.85rem" }}>
                <path d="M23 7l-7 5 7 5V7z" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
              <span style={{ fontSize: "1.1rem", fontWeight: "bold", marginBottom: "0.35rem" }}>
                Usar Cámara en Vivo
              </span>
              <span style={{ fontSize: "0.82rem", color: "#6b7280", textAlign: "center", lineHeight: "1.4" }}>
                Escaneo y reconocimiento automático en tiempo real
              </span>
            </button>

          </div>
        </div>
      )}

      {activeTab === "camera" && (
        <div className="edge-camera-workspace" style={{ animation: "fadeIn 0.3s ease" }}>
          {isStaff && (
            <div className="card" style={{ marginBottom: "1rem", padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", backgroundColor: "#f1f5f9", padding: "4px", borderRadius: "8px" }}>
                <button
                  type="button"
                  onClick={() => { stopCamera(); setCameraSourceType("local"); }}
                  style={{
                    flex: 1,
                    padding: "0.6rem 1rem",
                    borderRadius: "6px",
                    border: "none",
                    backgroundColor: cameraSourceType === "local" ? "white" : "transparent",
                    color: cameraSourceType === "local" ? "#0f172a" : "#64748b",
                    fontWeight: "600",
                    fontSize: "0.9rem",
                    boxShadow: cameraSourceType === "local" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                >
                  Cámara Local (USB)
                </button>
                <button
                  type="button"
                  onClick={() => { stopCamera(); setCameraSourceType("ip"); }}
                  style={{
                    flex: 1,
                    padding: "0.6rem 1rem",
                    borderRadius: "6px",
                    border: "none",
                    backgroundColor: cameraSourceType === "ip" ? "white" : "transparent",
                    color: cameraSourceType === "ip" ? "#0f172a" : "#64748b",
                    fontWeight: "600",
                    fontSize: "0.9rem",
                    boxShadow: cameraSourceType === "ip" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                >
                  Cámara por IP (HTTP/MJPEG)
                </button>
              </div>

              <label htmlFor="camera-device" style={{ display: "block", fontWeight: 700, marginBottom: "0.5rem" }}>
                {cameraSourceType === "ip" ? "URL del Stream de Cámara IP" : "Cámara conectada"}
              </label>

              {cameraSourceType === "ip" ? (
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", width: "100%" }}>
                  <input
                    type="url"
                    placeholder="Ej: http://192.168.1.100:8080/video o http://192.168.1.100:8080/shot.jpg"
                    value={ipCameraUrl}
                    onChange={(e) => setIpCameraUrl(e.target.value)}
                    style={{ 
                      flex: "1 1 280px", 
                      padding: "0.75rem", 
                      borderRadius: "8px", 
                      border: "1px solid #cbd5e1", 
                      background: "white",
                      fontSize: "0.9rem",
                      outline: "none"
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => { stopCamera(); startCamera(true); }}
                    style={{
                      padding: "0.75rem 1.5rem",
                      borderRadius: "8px",
                      border: "1px solid #cbd5e1",
                      backgroundColor: "#f8fafc",
                      color: "#334155",
                      fontWeight: "600",
                      fontSize: "0.9rem",
                      cursor: "pointer",
                      transition: "background-color 0.2s"
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "#e2e8f0"}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "#f8fafc"}
                  >
                    Conectar IP
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                  <select
                    id="camera-device"
                    value={selectedCameraId}
                    onChange={changeCamera}
                    style={{ flex: "1 1 280px", padding: "0.75rem", borderRadius: "8px" }}
                  >
                    {availableCameras.length === 0 && <option value="">Cámara predeterminada</option>}
                    {availableCameras.map((camera, index) => (
                      <option key={camera.deviceId} value={camera.deviceId}>
                        {camera.label || `Cámara ${index + 1}`}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="button secondary-button"
                    onClick={() => refreshCameraList().catch(() => setCameraError("No se pudieron consultar las cámaras."))}
                  >
                    Actualizar cámaras
                  </button>
                </div>
              )}
              <p className="muted-text" style={{ margin: "0.5rem 0 0", fontSize: "0.85rem" }}>
                {cameraSourceType === "ip" 
                  ? "Ingresa la URL del stream HTTP/MJPEG (ej: desde aplicaciones como IP Webcam en tu teléfono) y presiona Conectar." 
                  : "Conecta la cámara USB y selecciónala aquí. El navegador puede pedir permiso la primera vez."}
              </p>
            </div>
          )}
          <div className="card" style={{ padding: 0, overflow: "hidden", borderRadius: "16px" }}>
            <div className="camera-section" style={{ position: "relative" }}>
              {cameraOpen ? (
                <div className="camera-container" style={{
                  position: "relative",
                  width: "100%",
                  height: "clamp(620px, 85vh, 920px)",
                  borderRadius: "16px",
                  overflow: "hidden",
                  border: "4px solid var(--color-primary)",
                  backgroundColor: "#000"
                }}>
                  {scanError && (
                    <div style={{
                      position: "absolute",
                      top: "10px",
                      left: "10px",
                      right: "10px",
                      background: "#fef2f2",
                      color: "#991b1b",
                      border: "1px solid #fee2e2",
                      padding: "10px 16px",
                      borderRadius: "8px",
                      zIndex: 30,
                      fontSize: "13px",
                      fontWeight: "500",
                      boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)"
                    }}>
                      Error del servidor: {scanError}
                    </div>
                  )}
                  
                  {cameraSourceType === "ip" ? (
                    <img
                      ref={ipImageRef}
                      src={ipCameraUrl}
                      crossOrigin="anonymous"
                      alt="Stream de Cámara IP"
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                        display: "block"
                      }}
                      onError={() => setScanError("Error al cargar el stream de la cámara IP. Verifica la URL y la conexión.")}
                      onLoad={() => setScanError("")}
                    />
                  ) : (
                    <video
                      ref={videoRef}
                      autoPlay
                      playsInline
                      className="camera-preview"
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                        display: "block"
                      }}
                    />
                  )}

                  {trackingBoxes.map((box, i) => {
                    const [x, y, width, height] = box.bbox;
                    const sourceEl = cameraSourceType === "ip" ? ipImageRef.current : videoRef.current;
                    const videoW = sourceEl ? (cameraSourceType === "ip" ? sourceEl.naturalWidth : sourceEl.videoWidth) : 640;
                    const videoH = sourceEl ? (cameraSourceType === "ip" ? sourceEl.naturalHeight : sourceEl.videoHeight) : 480;
                    const pctX = (x / videoW) * 100;
                    const pctY = (y / videoH) * 100;
                    const pctW = (width / videoW) * 100;
                    const pctH = (height / videoH) * 100;

                    if (box.type === 'raw') {
                      return (
                        <div key={i} style={{
                          position: "absolute",
                          left: `${pctX}%`,
                          top: `${pctY}%`,
                          width: `${pctW}%`,
                          height: `${pctH}%`,
                          border: "2px solid rgba(255, 204, 0, 0.35)",
                          backgroundColor: "rgba(255, 204, 0, 0.04)",
                          zIndex: 5,
                          pointerEvents: "none",
                          borderRadius: "4px"
                        }} />
                      );
                    }

                    if (box.type === 'plate-voting') {
                      const progress = (box.votes || 1) / (box.votesNeeded || VOTES_NEEDED);
                      const colors = ["#eab308", "#f97316", "#22c55e"];
                      const colorIdx = Math.min(Math.floor(progress * 3), 2);
                      const borderColor = colors[colorIdx];
                      const dotsTotal = box.votesNeeded || VOTES_NEEDED;
                      const dotsFilled = box.votes || 1;
                      const dots = Array.from({ length: dotsTotal }, (_, di) =>
                        di < dotsFilled ? "●" : "○"
                      ).join(" ");

                      return (
                        <div key={i} style={{
                          position: "absolute",
                          left: `${pctX}%`,
                          top: `${pctY}%`,
                          width: `${pctW}%`,
                          height: `${pctH}%`,
                          border: `3px solid ${borderColor}`,
                          backgroundColor: `${borderColor}18`,
                          zIndex: 10,
                          pointerEvents: "none",
                          borderRadius: "6px",
                          boxShadow: `0 0 10px ${borderColor}60`,
                          transition: "border-color 0.3s, box-shadow 0.3s",
                        }}>
                          <span style={{
                            backgroundColor: borderColor,
                            color: "white",
                            padding: "2px 10px",
                            fontSize: "12px",
                            position: "absolute",
                            top: "-22px",
                            left: "-3px",
                            fontWeight: "bold",
                            borderRadius: "3px",
                            whiteSpace: "nowrap",
                            letterSpacing: "0.5px",
                          }}>
                            {box.text} &nbsp; {dots}
                          </span>
                        </div>
                      );
                    }
                  })}

                  {trackingBoxes.length === 0 && (
                    <div style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      right: 0,
                      height: "2px",
                      backgroundColor: "rgba(239, 68, 68, 0.8)",
                      boxShadow: "0 0 10px 2px rgba(239, 68, 68, 0.8)",
                      animation: "scan-fullscreen 2s infinite linear"
                    }}></div>
                  )}

                  {/* Capa superior de controles */}
                  <div style={{
                    position: "absolute",
                    top: "20px",
                    left: "20px",
                    right: "20px",
                    display: "flex",
                    justifyContent: "space-between",
                    zIndex: 20
                  }}>
                    {user?.rol !== "DISPOSITIVO" && (
                      <button
                        type="button"
                        onClick={() => { setActiveTab(null); }}
                        style={{
                          background: "rgba(0, 0, 0, 0.7)",
                          color: "white",
                          border: "1px solid rgba(255, 255, 255, 0.25)",
                          padding: "0.75rem 1.25rem",
                          borderRadius: "10px",
                          fontSize: "0.95rem",
                          fontWeight: "bold",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          transition: "all 0.2s"
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = "rgba(0, 0, 0, 0.9)"}
                        onMouseLeave={(e) => e.currentTarget.style.background = "rgba(0, 0, 0, 0.7)"}
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="19" y1="12" x2="5" y2="12"></line>
                          <polyline points="12 19 5 12 12 5"></polyline>
                        </svg>
                        Volver
                      </button>
                    )}

                    {user?.rol !== "DISPOSITIVO" && (
                      <button
                        type="button"
                        onClick={() => { setActiveModal("manual_lookup"); }}
                        style={{
                          background: "rgba(0, 0, 0, 0.7)",
                          color: "white",
                          border: "1px solid rgba(255, 255, 255, 0.25)",
                          padding: "0.75rem 1.25rem",
                          borderRadius: "10px",
                          fontSize: "0.95rem",
                          fontWeight: "bold",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          transition: "all 0.2s"
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = "rgba(0, 0, 0, 0.9)"}
                        onMouseLeave={(e) => e.currentTarget.style.background = "rgba(0, 0, 0, 0.7)"}
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="2" y="4" width="20" height="16" rx="2" ry="2"></rect>
                          <line x1="6" y1="8" x2="6" y2="8"></line>
                          <line x1="10" y1="8" x2="10" y2="8"></line>
                          <line x1="14" y1="8" x2="14" y2="8"></line>
                          <line x1="18" y1="8" x2="18" y2="8"></line>
                          <line x1="8" y1="12" x2="8" y2="12"></line>
                          <line x1="12" y1="12" x2="12" y2="12"></line>
                          <line x1="16" y1="12" x2="16" y2="12"></line>
                          <line x1="7" y1="16" x2="17" y2="16"></line>
                        </svg>
                        Registro Manual
                      </button>
                    )}
                  </div>

                  <div style={{ position: "absolute", bottom: "25px", left: "0", right: "0", textAlign: "center", zIndex: 20 }}>
                    <p className="camera-instruction" style={{ display: "inline-block", background: "rgba(0,0,0,0.8)", color: "white", padding: "10px 20px", borderRadius: "24px", margin: 0, fontSize: "0.95rem", fontWeight: "600" }}>
                      {trackingBoxes.some(b => b.type === 'plate-voting')
                        ? `Leyendo placa — mantén la cámara firme`
                        : "Buscando placa... apunta al vehículo"}
                    </p>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "3rem 2rem", border: "2px dashed rgba(21, 62, 117, 0.2)", borderRadius: "12px", margin: "2rem" }}>
                  <p className="muted-text" style={{ fontSize: "1.1rem" }}>Iniciando cámara...</p>
                  <button
                    type="button"
                    onClick={() => startCamera(true)}
                    style={{
                      marginTop: "1.5rem",
                      padding: "0.85rem 1.75rem",
                      backgroundColor: "var(--color-primary)",
                      color: "white",
                      border: "none",
                      borderRadius: "10px",
                      fontWeight: "bold",
                      cursor: "pointer"
                    }}
                  >
                    Reabrir Cámara en Vivo
                  </button>
                </div>
              )}
              <canvas ref={canvasRef} hidden />
              {cameraError && <p className="error-text" style={{ padding: "1rem" }}>{cameraError}</p>}
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Ingreso / Salida ──────────────────────────────────── */}
      {activeModal === "ingreso_egreso" && lookupResult && (
        <VehicleFoundModal
          lookupResult={lookupResult}
          setActiveModal={setActiveModal}
          setLookupResult={setLookupResult}
          accessZone={accessZone}
          setAccessZone={setAccessZone}
          accessError={accessError}
          setAccessError={setAccessError}
          registeringAccess={registeringAccess}
          handleRegisterAccess={handleRegisterAccess}
        />
      )}

      {/* ── Modal: Placa no registrada ───────────────────────────────── */}
      {activeModal === "plate_not_found" && (
        <PlateNotFoundModal
          manualPlate={manualPlate}
          setActiveModal={setActiveModal}
          setManualPlate={setManualPlate}
          activeTab={activeTab}
          startCamera={startCamera}
          reason={decisionReason}
        />
      )}
      {activeModal === "plate_request_sent" && (
        <PlateNotFoundModal
          manualPlate={manualPlate}
          setActiveModal={setActiveModal}
          setManualPlate={setManualPlate}
          activeTab={activeTab}
          startCamera={startCamera}
          requestSent
        />
      )}

      {/* ── Modal: Acceso confirmado ─────────────────────────────────── */}
      {activeModal === "access_confirmed" && autoAccessLog && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "420px", textAlign: "center" }}>
            <div style={{ padding: "2.5rem 1.5rem" }}>
              <div style={{ display: "flex", justifyContent: "center", marginBottom: "1rem" }}>
                {autoAccessLog.direction === "ENTRY" ? (
                  <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="#15803d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                  </svg>
                ) : (
                  <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="#b91c1c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="9" y1="15" x2="15" y2="15"></line>
                    <line x1="12" y1="12" x2="15" y2="15"></line>
                    <line x1="12" y1="18" x2="15" y2="15"></line>
                  </svg>
                )}
              </div>
              <h2 style={{
                color: autoAccessLog.direction === "ENTRY" ? "#15803d" : "#b91c1c",
                fontSize: "1.8rem",
                marginBottom: "0.5rem"
              }}>
                {autoAccessLog.direction === "ENTRY" ? "INGRESO REGISTRADO" : "SALIDA REGISTRADA"}
              </h2>
              {lookupResult && (
                <p style={{ fontFamily: "monospace", fontSize: "1.5rem", fontWeight: "bold", color: "var(--color-primary)", margin: "0.5rem 0" }}>
                  {lookupResult.license_plate}
                </p>
              )}
              <p style={{ color: "#6b7280", margin: "0.75rem 0 0" }}>
                Zona: <strong>{autoAccessLog.zone}</strong>
              </p>
              <p style={{ color: "#6b7280", margin: "0.25rem 0 0", fontSize: "1.1rem" }}>
                {new Date(autoAccessLog.timestamp).toLocaleTimeString("es-BO", { timeZone: "America/La_Paz", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </p>
              {autoAccessLog.media_status === "PENDING" && (
                <p className="muted-text" style={{ marginTop: "0.75rem" }}>Evidencia guardada localmente, pendiente de sincronización.</p>
              )}
              <p className="muted-text" style={{ marginTop: "1.5rem", fontSize: "0.85rem" }}>Volviendo a analizar en 5 segundos...</p>
            </div>
          </div>
        </div>
      )}


      {activeModal === "manual_lookup" && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "600px", width: "90%" }}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">Consulta manual</p>
                <h2>Buscar Placa de la Cámara</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => { setActiveModal(null); resetLookupState(); }}>
                Cerrar
              </button>
            </div>
            <div style={{ marginTop: "1.5rem" }}>
              <p className="muted-text" style={{ marginBottom: "1rem" }}>Ingresa los dígitos de la placa manualmente para validar el acceso:</p>
              <form className="manual-plate-form" onSubmit={handleLookup}>
                <label className="field-group">
                  <span>Número de placa</span>
                  <input
                    type="text"
                    placeholder="Ejemplo: 1234-ABC"
                    value={manualPlate}
                    onChange={(event) => setManualPlate(event.target.value)}
                    required
                    style={{ background: "white" }}
                  />
                </label>
                <button type="submit" disabled={lookupLoading}>
                  {lookupLoading ? "Validando..." : "Validar vehículo"}
                </button>
              </form>
              {lookupError && <p className="error-text" style={{ marginTop: "1rem" }}>{lookupError}</p>}
              {registerSuccess && <p className="success-text" style={{ marginTop: "1rem" }}>{registerSuccess}</p>}
            </div>
          </div>
        </div>
      )}

      {activeModal === "file" && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <div>
                <p className="eyebrow">Detección por Archivo</p>
                <h2>Subir del Dispositivo</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => { setActiveModal(null); setActiveTab(null); resetLookupState(); }}>
                Cerrar
              </button>
            </div>

            <div style={{ marginTop: "1.5rem" }}>
              <UploadImage onChange={handleImageSelected} />
              {fileName && <p style={{ marginTop: "0.5rem" }}>Archivo seleccionado: <strong>{fileName}</strong></p>}
            </div>

            {/* Resultados del análisis OCR */}
            {analysisPreview && (analysisPreview.ruta_imagen || analysisPreview.plate_crop) && (
              <div className="analysis-preview" style={{ marginTop: "1.5rem" }}>
                <p className="eyebrow">
                  {analysisPreview.status === "DETECTED" ? "✅ Placa detectada" : "⚠️ Detección fallida"}
                </p>
                <div className="analysis-images">
                  {analysisPreview.ruta_imagen && (
                    <div>
                      <p className="muted-text">Imagen analizada</p>
                      <img
                        className="vehicle-photo"
                        src={analysisPreview.ruta_imagen}
                        alt="Imagen anotada por OCR"
                      />
                    </div>
                  )}
                  {analysisPreview.plate_crop && (
                    <div>
                      <p className="muted-text">Recorte de placa</p>
                      <img
                        className="plate-crop-preview"
                        src={analysisPreview.plate_crop}
                        alt="Recorte de placa"
                      />
                    </div>
                  )}
                </div>
                {analysisPreview.placa_detectada && (
                  <p className="muted-text" style={{ marginTop: "1rem" }}>
                    Texto OCR: <strong>{analysisPreview.placa_detectada}</strong>
                    {" "}(confianza: {Math.round((analysisPreview.confianza || 0) * 100)}%)
                  </p>
                )}
                {analysisPreview.color_sugerido && (
                  <p className="muted-text" style={{ marginTop: "0.5rem" }}>
                    Color sugerido: <strong>{analysisPreview.color_sugerido}</strong>
                    {analysisPreview.confianza_color != null && (
                      <> ({Math.round(analysisPreview.confianza_color * 100)}%)</>
                    )}
                    {analysisPreview.metodo_color && <> · Método: {analysisPreview.metodo_color}</>}
                  </p>
                )}
                {analysisPreview.marca_sugerida && (
                  <p className="muted-text" style={{ marginTop: "0.5rem" }}>
                    Vehículo sugerido: <strong>{analysisPreview.marca_sugerida} {analysisPreview.modelo_sugerido || ""}</strong>
                    {analysisPreview.confianza_marca_modelo != null && (
                      <> ({Math.round(analysisPreview.confianza_marca_modelo * 100)}%)</>
                    )}
                    {analysisPreview.metodo_marca_modelo && <> · Método: {analysisPreview.metodo_marca_modelo}</>}
                  </p>
                )}
                {analysisPreview.metodo_tipo && (
                  <p className="muted-text" style={{ marginTop: "0.5rem" }}>
                    Tipo sugerido por RF-DETR: <strong>{analysisPreview.tipo_sugerido || "DESCONOCIDO"}</strong>
                    {analysisPreview.tipo_sugerido && analysisPreview.confianza_tipo != null && (
                      <> · {Math.round(analysisPreview.confianza_tipo * 100)} %</>
                    )}
                  </p>
                )}
              </div>
            )}

            {/*  integrada */}
            <div style={{ marginTop: "2rem", borderTop: "2px solid rgba(21, 62, 117, 0.1)", paddingTop: "1.5rem" }}>
              <p className="eyebrow">Registro manual</p>
              <h3>Buscar Placa de la Imagen</h3>
              <p className="muted-text">Si la imagen no pudo leerse automáticamente, ingresa los dígitos de la placa:</p>
              <form className="manual-plate-form" onSubmit={handleLookup}>
                <label className="field-group">
                  <span>Número de placa</span>
                  <input
                    type="text"
                    placeholder="Ejemplo: 1234-ABC"
                    value={manualPlate}
                    onChange={(event) => setManualPlate(event.target.value)}
                    required
                  />
                </label>
                <button type="submit" disabled={lookupLoading}>
                  {lookupLoading ? "Validando..." : "Validar vehículo"}
                </button>
              </form>
              {lookupError && <p className="error-text" style={{ marginTop: "1rem" }}>{lookupError}</p>}
              {registerSuccess && <p className="success-text" style={{ marginTop: "1rem" }}>{registerSuccess}</p>}
            </div>
          </div>
        </div>
      )}

      {activeModal === "snapshot" && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <div>
                <p className="eyebrow">Detección por Captura</p>
                <h2>Sacar Foto con Cámara</h2>
              </div>
              <button type="button" className="ghost-button" onClick={() => { setActiveModal(null); setActiveTab(null); resetLookupState(); }}>
                Cerrar
              </button>
            </div>

            <div style={{ marginTop: "1.5rem" }}>
              {cameraOpen ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem", alignItems: "center" }}>
                  <div className="camera-container" style={{
                    width: "100%",
                    height: "55vh",
                    minHeight: "350px",
                    borderRadius: "12px",
                    overflow: "hidden",
                    border: "2px solid var(--color-primary)",
                    backgroundColor: "#000",
                    position: "relative"
                  }}>
                    <video ref={videoRef} autoPlay playsInline style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                    <canvas ref={canvasRef} hidden />
                    
                    {/* Botón flotante de Registro Manual (igual que cámara en vivo) */}
                    <div style={{ position: "absolute", bottom: "15px", right: "15px", zIndex: 20 }}>
                      <button
                        type="button"
                        onClick={() => { setActiveModal("manual_lookup"); }}
                        style={{
                          background: "rgba(0, 0, 0, 0.7)",
                          color: "white",
                          border: "1px solid rgba(255, 255, 255, 0.25)",
                          padding: "0.75rem 1.25rem",
                          borderRadius: "10px",
                          fontSize: "0.95rem",
                          fontWeight: "bold",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          transition: "all 0.2s"
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = "rgba(0, 0, 0, 0.9)"}
                        onMouseLeave={(e) => e.currentTarget.style.background = "rgba(0, 0, 0, 0.7)"}
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="2" y="4" width="20" height="16" rx="2" ry="2"></rect>
                          <line x1="6" y1="8" x2="6" y2="8"></line>
                          <line x1="10" y1="8" x2="10" y2="8"></line>
                          <line x1="14" y1="8" x2="14" y2="8"></line>
                          <line x1="18" y1="8" x2="18" y2="8"></line>
                          <line x1="8" y1="12" x2="8" y2="12"></line>
                          <line x1="12" y1="12" x2="12" y2="12"></line>
                          <line x1="16" y1="12" x2="16" y2="12"></line>
                          <line x1="7" y1="16" x2="17" y2="16"></line>
                        </svg>
                        Registro Manual
                      </button>
                    </div>
                  </div>
                  <button
                    onClick={captureFromCamera}
                    disabled={lookupLoading}
                    style={{
                      padding: "0.8rem 2rem",
                      backgroundColor: "#22c55e",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      fontSize: "1rem",
                      fontWeight: "bold",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      margin: "0 auto"
                    }}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                      <circle cx="12" cy="13" r="4"></circle>
                    </svg>
                    {lookupLoading ? "Analizando..." : "Tomar Foto y Analizar"}
                  </button>
                  {cameraError && <p className="error-text">{cameraError}</p>}
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "2rem", border: "2px dashed rgba(21, 62, 117, 0.2)", borderRadius: "8px" }}>
                  <button
                    type="button"
                    onClick={() => startCamera(false)}
                    style={{
                      padding: "0.8rem 1.5rem",
                      backgroundColor: "var(--color-primary)",
                      color: "white",
                      border: "none",
                      borderRadius: "8px",
                      fontWeight: "bold",
                      cursor: "pointer"
                    }}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "8px", verticalAlign: "middle" }}>
                      <polygon points="23 7 16 12 23 17 23 7"></polygon>
                      <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                    </svg>
                    Abrir Cámara para Capturar
                  </button>
                </div>
              )}
            </div>

            {/* Resultados del análisis OCR */}
            {analysisPreview && (analysisPreview.ruta_imagen || analysisPreview.plate_crop) && (
              <div className="analysis-preview" style={{ marginTop: "1.5rem" }}>
                <p className="eyebrow">
                  {analysisPreview.status === "DETECTED" ? "✅ Placa detectada" : "⚠️ Detección fallida"}
                </p>
                <div className="analysis-images">
                  {analysisPreview.ruta_imagen && (
                    <div>
                      <p className="muted-text">Imagen analizada</p>
                      <img
                        className="vehicle-photo"
                        src={analysisPreview.ruta_imagen}
                        alt="Imagen anotada por OCR"
                      />
                    </div>
                  )}
                  {analysisPreview.plate_crop && (
                    <div>
                      <p className="muted-text">Recorte de placa</p>
                      <img
                        className="plate-crop-preview"
                        src={analysisPreview.plate_crop}
                        alt="Recorte de placa"
                      />
                    </div>
                  )}
                </div>
                {analysisPreview.placa_detectada && (
                  <p className="muted-text" style={{ marginTop: "1rem" }}>
                    Texto OCR: <strong>{analysisPreview.placa_detectada}</strong>
                    {" "}(confianza: {Math.round((analysisPreview.confianza || 0) * 100)}%)
                  </p>
                )}
                {analysisPreview.color_sugerido && (
                  <p className="muted-text" style={{ marginTop: "0.5rem" }}>
                    Color sugerido: <strong>{analysisPreview.color_sugerido}</strong>
                    {analysisPreview.confianza_color != null && (
                      <> ({Math.round(analysisPreview.confianza_color * 100)}%)</>
                    )}
                    {analysisPreview.metodo_color && <> · Método: {analysisPreview.metodo_color}</>}
                  </p>
                )}
                {analysisPreview.marca_sugerida && (
                  <p className="muted-text" style={{ marginTop: "0.5rem" }}>
                    Vehículo sugerido: <strong>{analysisPreview.marca_sugerida} {analysisPreview.modelo_sugerido || ""}</strong>
                    {analysisPreview.confianza_marca_modelo != null && (
                      <> ({Math.round(analysisPreview.confianza_marca_modelo * 100)}%)</>
                    )}
                    {analysisPreview.metodo_marca_modelo && <> · Método: {analysisPreview.metodo_marca_modelo}</>}
                  </p>
                )}
                {analysisPreview.metodo_tipo && (
                  <p className="muted-text" style={{ marginTop: "0.5rem" }}>
                    Tipo sugerido por RF-DETR: <strong>{analysisPreview.tipo_sugerido || "DESCONOCIDO"}</strong>
                    {analysisPreview.tipo_sugerido && analysisPreview.confianza_tipo != null && (
                      <> · {Math.round(analysisPreview.confianza_tipo * 100)} %</>
                    )}
                  </p>
                )}
              </div>
            )}

            {/* Registro manual integrado */}
            <div style={{ marginTop: "2rem", borderTop: "2px solid rgba(21, 62, 117, 0.1)", paddingTop: "1.5rem" }}>
              <p className="eyebrow">Registro manual</p>
              <h3>Buscar Placa de la Cámara</h3>
              <p className="muted-text">Si la cámara no detecta la placa, puedes ingresarla manualmente:</p>
              <form className="manual-plate-form" onSubmit={handleLookup}>
                <label className="field-group">
                  <span>Número de placa</span>
                  <input
                    type="text"
                    placeholder="Ejemplo: 1234-ABC"
                    value={manualPlate}
                    onChange={(event) => setManualPlate(event.target.value)}
                    required
                  />
                </label>
                <button type="submit" disabled={lookupLoading}>
                  {lookupLoading ? "Validando..." : "Validar vehículo"}
                </button>
              </form>
              {lookupError && <p className="error-text" style={{ marginTop: "1rem" }}>{lookupError}</p>}
              {registerSuccess && <p className="success-text" style={{ marginTop: "1rem" }}>{registerSuccess}</p>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default UploadPlate;


