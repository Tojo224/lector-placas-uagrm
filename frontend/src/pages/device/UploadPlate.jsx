import { useEffect, useRef, useState } from "react";
import UploadImage from "../../components/UploadImage";
import {
  createVehicle,
  lookupVehicleByPlate,
  uploadPlateImage,
  createAccessLog,
  createAutoAccessLog,
  createAutoAccessWithEvidence,
  getBrands,
  getVehicleTypes
} from "../../api/plates";
import { useAuth } from "../../hooks/useAuth";
import { formatPlate } from "../../utils/formatters";
import VehicleFoundModal from "../../components/UploadPlate/VehicleFoundModal";
import PlateNotFoundModal from "../../components/UploadPlate/PlateNotFoundModal";

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

function UploadPlate() {
  const { user } = useAuth();
  const isAdmin = user?.rol === "ADMINISTRATIVE" || user?.rol === "ADMINISTRADOR";
  const isStaff = user?.rol === "ADMINISTRADOR" || user?.rol === "OPERADOR";
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const modelRef = useRef(null);
  const requestRef = useRef(null);
  const requestControllerRef = useRef(null);
  const detectionTimerRef = useRef(null);
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
  const activeModalRef = useRef(null);

  useEffect(() => {
    activeModalRef.current = activeModal;
  }, [activeModal]);

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
  }, [activeTab, activeModal]);

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
        result = await lookupVehicleByPlate(plateValue);
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
            ? await createAutoAccessWithEvidence({
                vehicle_id: result.id,
                zone: accessZone,
                notes: ""
              }, evidence)
            : await createAutoAccessLog({
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
            analysisResult = await uploadPlateImage(form);
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
    const normalizedPlate = formatPlate(manualPlate);
    await handleLookupPlate(normalizedPlate);
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
      const analysis = await uploadPlateImage(formData);
      setAnalysisPreview(analysis);

      if (analysis?.placa_normalizada) {
        // OCR exitoso con formato boliviano confirmado
        setManualPlate(analysis.placa_normalizada);
        await handleLookupPlate(analysis.placa_normalizada, file, analysis);
      } else if (analysis?.placa_detectada) {
        // OCR detectó texto pero no cumple el formato: rellenar campo para corrección manual
        const rawClean = analysis.placa_detectada.replace(/[^A-Z0-9]/gi, "").toUpperCase();
        setManualPlate(rawClean);
        setLookupError(
          `OCR detecto: "${analysis.placa_detectada}" — ${analysis.mensaje || "Verifica y corrige el numero de placa si es necesario."}`
        );
      } else {
        setLookupError(analysis?.mensaje || "No se pudo detectar una placa en la imagen.");
      }
    } catch (error) {
      setLookupError(error?.response?.data?.detail || "No se pudo analizar la imagen.");
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
    if (!videoRef.current || !canvasRef.current || !streamRef.current) return;
    // Si hay un modal activo en pantalla, pausar el análisis OCR para no saturar la CPU,
    // pero mantener la cámara encendida.
    if (activeModalRef.current !== null) {
      requestRef.current = null;
      if (streamRef.current) detectionTimerRef.current = setTimeout(detectFrame, 1000);
      return;
    }
    if (requestRef.current === "processing") return;

    requestRef.current = "processing";
    const canvas = canvasRef.current;

    // OPT-A/D: Resolución del canvas alineada con MAX_REALTIME_DIM del backend (480px)
    const MAX_DETECTION_DIM = 480;
    let videoW = videoRef.current.videoWidth || 480;
    let videoH = videoRef.current.videoHeight || 360;

    if (videoW === 0) {
      requestRef.current = null;
      if (streamRef.current) detectionTimerRef.current = setTimeout(detectFrame, 1000);
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
    context.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);

    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    // El siguiente frame se toma al terminar la petición anterior. Una pausa
    // corta evita perder al vehículo mientras cruza el encuadre.
    let nextInterval = 250;

    try {
      // OPT-F: Convertir a escala de grises en el canvas antes de enviar.
      // El JPEG en gris es ~3x más pequeño que en color y el backend igual hace
      // cvtColor internamente — enviarlo en gris ahorra bytes de red + un cvtColor.
      const grayCtx = canvas.getContext("2d");
      const imageData = grayCtx.getImageData(0, 0, canvas.width, canvas.height);
      const d = imageData.data;
      for (let i = 0; i < d.length; i += 4) {
        const luma = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        d[i] = d[i + 1] = d[i + 2] = luma;
      }
      grayCtx.putImageData(imageData, 0, 0);
      // JPEG 80%: balance entre tamaño de archivo y calidad para OCR
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.80));
      // Restaurar contexto en color para el siguiente frame (solo afecta el canvas off-screen)
      context.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      if (blob) {
        const formData = new FormData();
        formData.append("file", blob, "frame.jpg");
        const analysis = await uploadPlateImage(formData, true, controller.signal);

        const normalizedText = analysis.placa_normalizada
          ? analysis.placa_normalizada
          : (analysis.placa_detectada
              ? analysis.placa_detectada.replace(/[^A-Z0-9]/gi, "").toUpperCase()
              : null);

        // --- Sistema de votación por consenso ---
        // Un texto solo se confirma cuando aparece N veces seguidas
        const voteMap = voteMapRef.current;
        const now = Date.now();

        if (normalizedText && normalizedText.length >= 4) {
          // Texto detectado: sumar voto
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

          // Limpiar textos que no han aparecido en los últimos 4 frames (~4s)
          for (const [key, val] of voteMap.entries()) {
            if (key !== normalizedText && now - val.lastFrameTs > 4000) {
              voteMap.delete(key);
            }
          }

          // Verificar si algún texto alcanzó el umbral de votos
          const winner = [...voteMap.entries()].find(
            ([, v]) => v.isValidFormat && (
              v.count >= VOTES_NEEDED ||
              // Una lectura muy fuerte se captura inmediatamente: en movimiento
              // puede no existir un segundo fotograma nítido.
              (v.count === 1 && v.score >= 0.88)
            )
          );

          if (winner) {
            // Confirmado por consenso → auto-captura
            const [, winnerData] = winner;
            // El polling usa 640px para OCR. Solo al confirmar capturamos una
            // evidencia panoramica a la resolucion nativa de la camara.
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
            setTrackingBoxes([]);
            setAnalysisPreview(analysis);
            setManualPlate(normalizedText);
            handleLookupPlate(normalizedText, evidenceBlob || blob, analysis);
            return;
          }

          // Mostrar caja con contador de votos
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
              text: analysis.placa_normalizada || analysis.placa_detectada,
              votes: entry ? entry.count : 1,
              votesNeeded: VOTES_NEEDED,
              type: 'plate-voting',
            });
          }
          setScanError("");
          setTrackingBoxes(newBoxes);

          // OPT-D: Throttle 500ms (antes 600ms) — más frames sin afectar OCR CPU
          nextInterval = 500;

        } else {
          // Sin texto válido: limpiar votos viejos y reducir frecuencia
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
        setScanError(e.response?.data?.detail || e.mensaje || "Error al procesar la imagen.");
        setTrackingBoxes([]);
      }
    } finally {
      clearTimeout(timeoutId);
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
    requestRef.current = null;
    if (streamRef.current) {
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
      setCameraError("No se pudo abrir la camara del dispositivo.");
      console.error(error);
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
    if (!videoRef.current || !canvasRef.current) {
      return;
    }

    const canvas = canvasRef.current;
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const context = canvas.getContext("2d");
    context.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) {
      setCameraError("No se pudo capturar la imagen desde la camara.");
      return;
    }

    const formData = new FormData();
    formData.append("file", blob, "captura-placa.jpg");

    try {
      setLookupLoading(true);
      const analysis = await uploadPlateImage(formData);
      setAnalysisPreview(analysis);
      if (analysis?.placa_normalizada) {
        setManualPlate(analysis.placa_normalizada);
        await handleLookupPlate(analysis.placa_normalizada);
      } else {
        setLookupError(analysis?.mensaje || "No se pudo detectar una placa desde la camara.");
      }
    } catch (error) {
      setLookupError(error?.response?.data?.detail || "No se pudo analizar la captura.");
    } finally {
      setLookupLoading(false);
      stopCamera();
    }
  };

  const handleVehicleSubmit = async (event) => {
    event.preventDefault();
    setRegisterError("");
    setRegisterSuccess("");

    try {
      const payload = {
        ...vehicleForm,
        license_plate: formatPlate(vehicleForm.license_plate),
        registered_by_user_id: user?.id,
        owner: ownerForm
      };

      const createdVehicle = await createVehicle(payload);
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
    if (!lookupResult?.id) return;
    try {
      setRegisteringAccess(true);
      setAccessError("");
      const log = await createAutoAccessLog({
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
      {activeTab === null && (
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "55vh",
          padding: "2rem"
        }}>
          <h2 style={{ color: "var(--color-primary)", marginBottom: "0.5rem", fontSize: "1.8rem", textAlign: "center" }}>
            Selecciona una opción
          </h2>
          <p className="muted-text" style={{ marginBottom: "2.5rem", fontSize: "1.1rem", textAlign: "center" }}>
            Elige el método de detección de placas para comenzar el control de acceso
          </p>

          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "2rem",
            width: "100%",
            maxWidth: "700px"
          }}>
            <button
              type="button"
              onClick={() => { setActiveTab("image"); setActiveModal("file"); resetLookupState(); }}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "2.5rem 1.5rem",
                borderRadius: "20px",
                border: "2px solid rgba(21, 62, 117, 0.15)",
                background: "white",
                color: "var(--color-primary)",
                cursor: "pointer",
                transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                boxShadow: "0 10px 25px rgba(21, 62, 117, 0.05)"
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-5px)";
                e.currentTarget.style.borderColor = "var(--color-primary)";
                e.currentTarget.style.background = "#f8fafc";
                e.currentTarget.style.boxShadow = "0 15px 30px rgba(21, 62, 117, 0.1)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.borderColor = "rgba(21, 62, 117, 0.15)";
                e.currentTarget.style.background = "white";
                e.currentTarget.style.boxShadow = "0 10px 25px rgba(21, 62, 117, 0.05)";
              }}
            >
              <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-primary)", marginBottom: "1.2rem" }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span style={{ fontSize: "1.3rem", fontWeight: "bold", marginBottom: "0.5rem" }}>
                Subir Imagen de Placa
              </span>
              <span style={{ fontSize: "0.9rem", color: "#6b7280", textAlign: "center", lineHeight: "1.4" }}>
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
                padding: "2.5rem 1.5rem",
                borderRadius: "20px",
                border: "2px solid rgba(21, 62, 117, 0.15)",
                background: "white",
                color: "var(--color-primary)",
                cursor: "pointer",
                transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                boxShadow: "0 10px 25px rgba(21, 62, 117, 0.05)"
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-5px)";
                e.currentTarget.style.borderColor = "var(--color-primary)";
                e.currentTarget.style.background = "#f8fafc";
                e.currentTarget.style.boxShadow = "0 15px 30px rgba(21, 62, 117, 0.1)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.borderColor = "rgba(21, 62, 117, 0.15)";
                e.currentTarget.style.background = "white";
                e.currentTarget.style.boxShadow = "0 10px 25px rgba(21, 62, 117, 0.05)";
              }}
            >
              <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-primary)", marginBottom: "1.2rem" }}>
                <path d="M23 7l-7 5 7 5V7z" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
              <span style={{ fontSize: "1.3rem", fontWeight: "bold", marginBottom: "0.5rem" }}>
                Usar Cámara en Vivo
              </span>
              <span style={{ fontSize: "0.9rem", color: "#6b7280", textAlign: "center", lineHeight: "1.4" }}>
                Escaneo y reconocimiento automático en tiempo real
              </span>
            </button>

          </div>
        </div>
      )}

      {activeTab === "camera" && (
        <div style={{ animation: "fadeIn 0.3s ease" }}>
          {isStaff && (
            <div className="card" style={{ marginBottom: "1rem", padding: "1rem 1.25rem" }}>
              <label htmlFor="camera-device" style={{ display: "block", fontWeight: 700, marginBottom: "0.5rem" }}>
                Cámara conectada
              </label>
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
              <p className="muted-text" style={{ margin: "0.5rem 0 0", fontSize: "0.85rem" }}>
                Conecta la cámara USB y selecciónala aquí. El navegador puede pedir permiso la primera vez.
              </p>
            </div>
          )}
          <div className="card" style={{ padding: 0, overflow: "hidden", borderRadius: "16px" }}>
            <div className="camera-section" style={{ position: "relative" }}>
              {cameraOpen ? (
                <div className="camera-container" style={{
                  position: "relative",
                  width: "100%",
                  height: "75vh",
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
                      background: "rgba(220, 38, 38, 0.95)",
                      color: "white",
                      padding: "8px 16px",
                      borderRadius: "8px",
                      zIndex: 30,
                      fontSize: "13px",
                      fontWeight: "bold",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.3)"
                    }}>
                      ⚠️ Error del servidor: {scanError}
                    </div>
                  )}
                  
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

                  {trackingBoxes.map((box, i) => {
                    const [x, y, width, height] = box.bbox;
                    const videoW = videoRef.current ? videoRef.current.videoWidth : 640;
                    const videoH = videoRef.current ? videoRef.current.videoHeight : 480;
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
                {new Date(autoAccessLog.timestamp).toLocaleTimeString("es-BO", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </p>
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


